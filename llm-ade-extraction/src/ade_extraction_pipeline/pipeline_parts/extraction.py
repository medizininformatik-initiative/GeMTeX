from typing import List, Any

from pydantic import BaseModel, Field, create_model

from pydantic_ai import Agent, AgentRunResult
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.providers.ollama import OllamaProvider


# class Diagnose(BaseModel):
#     text: str = Field(..., description="Die konkrete Referenz der Diagnose im Text.")
#
#
# class Medikation(BaseModel):
#     text: str = Field(
#         ...,
#         description="Die konkrete Referenz einer Medikation oder eines Wirkstoffs im Text.",
#     )
#
#
# class TextAnnotationen(BaseModel):
#     diagnosen: List[Diagnose]
#     medikationen: List[Medikation]

def create_models_from_config(config: dict):
    annotation_dict = {}
    for k, v in config.get("TextAnnotationen", {}).items():
        annotation_dict[k] = (list, create_model(
            k,
            text=(str, Field(..., description=v["prompt"])),
        ))
    return create_model("TextAnnotationen", **annotation_dict)



def run_agent_on_query(query: str, config: dict) -> AgentRunResult[Any]:
    agent = Agent(
        model=OpenAIChatModel(
            model_name="alias-large",
            # provider=OllamaProvider(base_url='http://localhost:11434/v1'),
            provider=OpenAIProvider(
                base_url="https://api.helmholtz-blablador.fz-juelich.de/v1/",
                api_key=config.get("pydantic-ai").get("api_key", ""),
            ),
        ),
        system_prompt=config.get("prompt"),
        # output_type=TextAnnotationen,
        output_type=create_models_from_config(config.get("pydantic")),
    )
    return agent.run_sync(query)
