"""Authoring adapters for the existing canonical communication capabilities."""
from copy import deepcopy
from backend.runtime_v3.remote_models import CommunicationCapabilities

CHANNELS = ('text_message', 'voice_call', 'letter', 'courier', 'telegram', 'landline', 'magic')
DEFAULT_DELIVERY = dict(text_message='instant', voice_call='live', letter='delayed',
                        courier='delayed', telegram='delayed', landline='live', magic='instant')
PRESETS = dict(none=(), letters=('letter','courier'),
               **{'1939':('letter','telegram','landline')},
               modern=('text_message','voice_call'), fantastic=('magic',), custom=())


def catalog():
    return {name: CommunicationCapabilities(preset=name, presentation='phone' if name=='modern' else 'none',
        delivery_policy={key:DEFAULT_DELIVERY[key] for key in channels},
        **{key:True for key in channels}).model_dump() for name,channels in PRESETS.items()}


def apply_explicit(state):
    """Protect explicit generation input, including recovered author revisions."""
    selected=state.get('creation_settings',{}).get('communication')
    if selected is not None:
        state.setdefault('world',{})['communication']=CommunicationCapabilities.model_validate(selected).model_dump()
    return state


def edit_profile(state, value):
    state=deepcopy(state)
    profile=CommunicationCapabilities.model_validate(value).model_dump()
    state.setdefault('world',{})['communication']=profile
    state.setdefault('creation_settings',{})['communication']=deepcopy(profile)
    paths=state.setdefault('authoring',{}).setdefault('manual_paths',[])
    if '/world/communication' not in paths:paths.append('/world/communication')
    return state
