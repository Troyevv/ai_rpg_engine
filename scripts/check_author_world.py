"""Offline compiler check, or an explicitly enabled, bounded live generation.

No key is read and no provider is called without --allow-paid. A fresh isolated
database is required; interrupted runs are never retried by this command.
"""
import argparse
import getpass
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    source=parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--document',type=Path,help='Compile an author JSON document offline')
    source.add_argument('--live-source',type=Path,help='Read a UTF-8 idea for a separately authorized live test')
    parser.add_argument('--allow-paid',action='store_true')
    parser.add_argument('--database',type=Path)
    parser.add_argument('--model',default='deepseek-flash')
    parser.add_argument('--max-requests',type=int,default=12)
    parser.add_argument('--max-total-tokens',type=int,default=150000)
    args=parser.parse_args()
    if args.document:
        from backend.services.world_authoring_compiler import compile_document
        result=compile_document(json.loads(args.document.read_text()))
        print(json.dumps(dict(valid=True,entities=len(result.id_map),diagnostics=result.diagnostics),ensure_ascii=False))
        return
    if not args.allow_paid:
        parser.error('Live testing needs new explicit authorization and --allow-paid; no API call made.')
    if not args.database or args.database.exists():
        parser.error('--database must name a new isolated database')
    if args.max_requests<1 or args.max_total_tokens<1:
        parser.error('budgets must be positive')
    from backend.repositories.preparation import Repository
    from backend.services.preparation import Preparation,Handle
    from backend.services.world_generation import run
    from context_builder import estimate
    from llm import chat_stream
    text=args.live_source.read_text(encoding='utf-8')
    config=dict(provider='deepseek',model=args.model,context_length=131072,max_tokens=12000,
        update_tokens=4096,temperature=.8,_draft_task='world_staged',_draft_input=text,
        _creation={'cast_preset':'small'})
    repo=Repository(str(args.database));wid=repo.create_workspace('Explicit live authoring check')['id']
    jid=repo.begin_preparation(wid,'draft_world_staged',text,config,0)
    calls=0;reserved=0
    def bounded(**kw):
        nonlocal calls,reserved
        upper=estimate(kw['messages'])+kw['max_tokens']
        if calls>=args.max_requests or reserved+upper>args.max_total_tokens:
            raise RuntimeError('Live harness request/token reservation budget exhausted')
        calls+=1;reserved+=upper
        yield from chat_stream(**kw)
    key=getpass.getpass('Temporary DeepSeek key (not stored): ')
    run(Preparation(repo),jid,config,key,Handle(),None,bounded)
    key=''
    status=repo.preparation_job(jid)['status']
    print(json.dumps(dict(job=jid,status=status,requests=calls,conservative_reserved_tokens=reserved,
        note='Reservations are estimates, not billed usage; inspect the existing request log. No automatic resume.'),ensure_ascii=False))
    if status!='saved':raise SystemExit(1)


if __name__=='__main__':main()
