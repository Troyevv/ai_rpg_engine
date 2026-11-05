"""Controlled LLM for the real browser generation/recovery path. No production imports."""
import json
from threading import Event
from test_initial_draft_v4 import rich
from backend.services.draft_creative import MARKER as CREATIVE
from backend.services.draft_completeness import MARKER as REVIEW
from draft_provider_fixture import creative_noop

class IdeaProvider:
    def __init__(self, fail_review=False, custom_calendar=False):
        self.fail_review=fail_review
        self.custom_calendar=custom_calendar
        self.gate=Event()
        self.world_calls=0
        self.review_calls=0

    def matches(self,kwargs):
        return 'ATELIER190' in '\n'.join(m['content'] for m in kwargs['messages'])

    def stream(self,kwargs):
        system=kwargs['messages'][0]['content']
        if system.startswith(CREATIVE):
            yield creative_noop(kwargs['messages'])
        elif system.startswith(REVIEW):
            self.review_calls+=1
            if not self.gate.wait(30):raise RuntimeError('Idea review gate timed out')
            if self.fail_review and self.review_calls==1:
                # Exercise SDK -> transport diagnostic conversion with real HTTP metadata.
                import httpx
                from openai import OpenAI
                from unittest.mock import patch
                import llm
                def client(**kw):
                    return OpenAI(**kw,http_client=httpx.Client(transport=httpx.MockTransport(
                        lambda request:httpx.Response(502,json={'error':{'message':'fixture upstream unavailable'}}))))
                with patch('llm.OpenAI',side_effect=client):yield from llm.chat_stream(**kwargs)
            else:yield '{"issues":[]}'
        else:
            self.world_calls+=1
            state=rich()
            state['campaign']['title']='ATELIER190 · Город друзей'
            if self.custom_calendar:state['world_clock']['calendar']={}
            yield json.dumps(state,ensure_ascii=False)
