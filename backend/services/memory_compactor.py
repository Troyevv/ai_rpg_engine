"""Adaptive, POV-isolated summarization; source text is split, never truncated."""
from copy import deepcopy
from context_builder import encoded, estimate
from llm import OutputLimitReached


class MemoryDeferred(ValueError):
    pass


def output_budget(config):
    return max(256,min(2048,config['context_length']//4))


class Compactor:
    def __init__(self,prompt,config,generate,cancelled):
        self.prompt=prompt
        self.generate=generate
        self.cancelled=cancelled
        self.budget=config['context_length']-output_budget(config)-256
        self.target=min(4000,max(512,config['context_length']//8))
        # Reuse successful objective/POV sub-results if a smaller batch is needed.
        self.cache={}

    def messages(self,previous,entries,pov,repair=False):
        target=self.target//2 if repair else self.target
        instruction=(f'\nОбнови память целиком, не дописывай бесконечную хронику. Максимум {target} символов. '
                     'Сохрани существенные события, обязательства, причинные связи и границы знаний. '
                     'Фрагменты одного хода не являются новыми событиями. Верни только итоговую память.')
        if repair:instruction+=' Предыдущая попытка не завершилась или превысила размер. Сожми сильнее.'
        return [{'role':'system','content':self.prompt+instruction},
                {'role':'user','content':encoded({'POV':pov,'previous_memory':previous,'turns':entries})}]

    def split(self,entries):
        if len(entries)>1:
            middle=len(entries)//2
            return entries[:middle],entries[middle:]
        entry=entries[0]
        key=max((k for k,v in entry.items() if isinstance(v,str) and k!='_fragment'),key=lambda k:len(entry[k]),default=None)
        if key is None or len(entry[key])<128:
            raise MemoryDeferred('Недостаточно контекста даже для минимального фрагмента памяти.')
        middle=len(entry[key])//2
        left,right=deepcopy(entry),deepcopy(entry)
        left[key],right[key]=entry[key][:middle],entry[key][middle:]
        # Do not duplicate the other textual fields (e.g. player input).
        for k,v in right.items():
            if k not in (key,'_fragment') and isinstance(v,str):right[k]=''
        left['_fragment']=entry.get('_fragment','')+'L'
        right['_fragment']=entry.get('_fragment','')+'R'
        return [left],[right]

    def fold(self,previous,entries,pov):
        if self.cancelled.is_set():return previous
        key=encoded([pov,previous,entries])
        if key in self.cache:return self.cache[key]
        messages=self.messages(previous,entries,pov)
        if estimate(messages)>self.budget:
            # An old large summary is also automatically re-compressed, in pieces
            # if necessary. Actor scope is unchanged throughout recursion.
            if previous and estimate(self.messages(previous,[],pov))>self.budget//2:
                previous=self.fold('',[{'previous_memory':previous}],pov)
                if self.cancelled.is_set():return previous
                messages=self.messages(previous,entries,pov)
            if estimate(messages)>self.budget:
                left,right=self.split(entries)
                result=self.fold(self.fold(previous,left,pov),right,pov)
                self.cache[key]=result
                return result
        for attempt in range(2):
            if self.cancelled.is_set():return previous
            messages=self.messages(previous,entries,pov,repair=bool(attempt))
            if estimate(messages)>self.budget:break
            try:result=''.join(self.generate(messages)).strip()
            except OutputLimitReached:result=''
            if self.cancelled.is_set():return previous
            if result and len(result)<=self.target:
                self.cache[key]=result
                return result
        if len(entries)>1:
            left,right=self.split(entries)
            result=self.fold(self.fold(previous,left,pov),right,pov)
            self.cache[key]=result
            return result
        raise MemoryDeferred('Модель не смогла сжать минимальный пакет; движок повторит попытку автоматически.')

    def summarize(self,previous,turns,pov):
        entries=[{'sequence':t['sequence'],'player':t['user_text'],'narrator':t['assistant_text']} for t in turns]
        return self.fold(previous,entries,pov)
