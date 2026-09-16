"""Bounded request context, unbounded document streaming until the model finishes."""
from copy import deepcopy
from context_builder import estimate
from llm import OutputLimitReached

INSTRUCTION = ('Продолжи документ ровно с места обрыва. Не начинай заново, не повторяй уже написанное, '
               'не добавляй вступление о продолжении. Заверши незаконченные слова/предложения и все оставшиеся '
               'разделы исходного задания. Верни только продолжение Markdown. Уже выданный текст сохранён.')


def request_context(original, text, context_length, requested_output):
    """Keep source/template intact; slide only generated text when the context fills."""
    messages=deepcopy(original)
    if text:
        messages += [{'role':'assistant','content':''},{'role':'user','content':INSTRUCTION}]
    # Leave room for a useful tail and provider framing. Estimate is deliberately conservative.
    available=context_length-estimate(messages)-512
    tail_reserve=min(2048,available//3) if text else 0
    output=min(requested_output,available-tail_reserve)
    if output<256:
        # This byte heuristic is not the model tokenizer. Never reject intact
        # source material on its estimate alone; let the provider validate it.
        # Use a modest output budget, and preserve a tail for continuation.
        if text:
            messages[-2]['content']=text[-1024:]
        return messages,min(requested_output,1024)
    if text:
        budget=context_length-output-512
        lo,hi=0,len(text)
        while lo<hi:
            mid=(lo+hi+1)//2
            messages[-2]['content']=text[-mid:]
            if estimate(messages)<=budget:lo=mid
            else:hi=mid-1
        messages[-2]['content']=text[-lo:] if lo else ''
        if not lo:messages[-2]['content']=text[-1024:]
    return messages,output


def stream_document(original, context_length, max_tokens, generate, cancelled):
    text=''
    requested=max_tokens
    while not cancelled.is_set():
        messages,limit=request_context(original,text,context_length,requested)
        fragment=''
        try:
            for chunk in generate(messages,limit):
                if cancelled.is_set():return
                fragment+=chunk
                yield chunk
        except OutputLimitReached:
            if cancelled.is_set():return
            if not fragment.strip():
                # Thinking can consume a small output budget without visible text.
                grown=min(32000,requested*2)
                if grown<=requested or request_context(original,text,context_length,grown)[1]<=limit:
                    raise ValueError('Модель исчерпала доступный ответ на размышления, не выдав текст. Уменьши Thinking или увеличь контекст.')
                requested=grown
                continue
            if text.endswith(fragment):
                raise ValueError('Модель повторяет предыдущий фрагмент вместо продолжения. Полученный текст сохранён.')
            text+=fragment
            continue
        return
