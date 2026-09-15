from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, SecretStr

class DTO(BaseModel):
    model_config = ConfigDict(extra='forbid')

class ModelConfig(DTO):
    provider: Literal['local', 'deepseek'] = 'local'
    model: str = Field(min_length=1, max_length=300)
    context_length: int = Field(default=32768, ge=8192, le=131072)
    temperature: float = Field(default=0.8, ge=0, le=1.5)
    max_tokens: int = Field(default=2000, ge=256, le=32000)
    update_tokens: int = Field(default=4096, ge=1024, le=16000)

class Credential(DTO):
    api_key: SecretStr | None = None
    def key(self):
        return self.api_key.get_secret_value() if self.api_key else None

class Generation(Credential):
    kind: Literal['idea', 'summary']
    text: str = Field(default='', max_length=100000)
    revision: int = Field(ge=0)
    config: ModelConfig

class Turn(Credential):
    kind: Literal['start', 'turn', 'regenerate'] = 'turn'
    text: str = Field(default='', max_length=100000)
    revision: int = Field(ge=0)
    config: ModelConfig

class Retry(Credential):
    config: ModelConfig

class Named(DTO):
    name: str = Field(min_length=1, max_length=120, pattern=r'\S')

class World(Named):
    markdown: str = Field(min_length=1, max_length=2000000)

class Revision(DTO):
    revision: int = Field(ge=0)

class Scene(DTO):
    time: str = Field(max_length=120)
    location: str = Field(max_length=200)
    present_ids: list[str] = Field(max_length=100)
    revision: int = Field(ge=0)

class Models(Credential):
    provider: Literal['local', 'deepseek']

class Load(DTO):
    model: str = Field(min_length=1, max_length=300)
    context_length: int = Field(default=16384, ge=8192, le=131072)
    eval_batch_size: Literal[256, 512, 1024, 2048] = 512
    flash_attention: bool = True
    offload_kv_cache_to_gpu: bool = True

class Preferences(DTO):
    idea: ModelConfig
    summary: ModelConfig
    game: ModelConfig
    local: Load
    font_size: int = Field(default=18, ge=14, le=24)
    line_height: float = Field(default=1.8, ge=1.3, le=2.2)
    reading_width: int = Field(default=800, ge=600, le=1100)
    link_names: bool = True

class Markdown(DTO):
    text: str = Field(max_length=2000000)
    save_id: int | None = None
    world_id: int | None = None
    link_names: bool = True
