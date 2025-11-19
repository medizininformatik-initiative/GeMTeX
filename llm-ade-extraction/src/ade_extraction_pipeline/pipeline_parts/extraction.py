from enum import Enum
from importlib import import_module
from typing import Any, Type, Optional

from pydantic import BaseModel, Field, create_model

from pydantic_ai import Agent, AgentRunResult


def json_schema_to_base_model(schema: dict[str, Any]) -> Type[BaseModel]:
    type_mapping: dict[str, type] = {
        "string": str,
        "integer": int,
        "number": float,
        "boolean": bool,
        "array": list,
        "object": dict,
    }

    properties = schema.get("properties", {})
    required_fields = schema.get("required", [])
    model_fields = {}

    def process_field(field_name: str, field_props: dict[str, Any]) -> tuple:
        """Recursively processes a field and returns its type and Field instance."""
        json_type = field_props.get("type", "string")
        enum_values = field_props.get("enum")

        # Handle Enums
        if enum_values:
            enum_name: str = f"{field_name.capitalize()}Enum"
            field_type = Enum(enum_name, {v: v for v in enum_values})
        # Handle Nested Objects
        elif json_type == "object" and "properties" in field_props:
            field_type = json_schema_to_base_model(
                field_props
            )  # Recursively create submodel
        # Handle Arrays with Nested Objects
        elif json_type == "array" and "items" in field_props:
            item_props = field_props["items"]
            if item_props.get("type") == "object":
                item_type: type[BaseModel] = json_schema_to_base_model(item_props)
            else:
                item_type: type = type_mapping.get(item_props.get("type"), Any)
            field_type = list[item_type]
        else:
            field_type = type_mapping.get(json_type, Any)

        # Handle default values and optionality
        default_value = field_props.get("default", ...)
        nullable = field_props.get("nullable", False)
        description = field_props.get("title", "")

        if nullable:
            field_type = Optional[field_type]

        if field_name not in required_fields:
            default_value = field_props.get("default", None)

        return field_type, Field(default_value, description=description)

    # Process each field
    for field_name, field_props in properties.items():
        model_fields[field_name] = process_field(field_name, field_props)

    return create_model(schema.get("title", "DynamicModel"), **model_fields)


def get_full_module_name_and_class(module_type: str, config_impl_name: str):
    _provider_model_dict = {
        "model": "models",
        "models": "models",
        "provider": "providers",
        "providers": "providers",
    }
    return (
        f"pydantic_ai.{_provider_model_dict.get(module_type)}.{'.'.join(config_impl_name.split('.')[:-1])}",
        config_impl_name.split(".")[-1],
    )


def run_agent_on_query(
    query: str, config: dict, api_key: Optional[str]
) -> AgentRunResult[Any]:
    _ai_model_dict = config.get("pydantic-ai").get("model")
    _ai_provider_dict = config.get("pydantic-ai").get("provider")

    _ai_model_module, _ai_model_name = get_full_module_name_and_class(
        "models", _ai_model_dict.get("implementation", "openai.OpenAIChatModel")
    )
    _ai_provider_module, _ai_provider_name = get_full_module_name_and_class(
        "providers", _ai_provider_dict.get("implementation", "openai.OpenAIProvider")
    )
    _pydantic_model = json_schema_to_base_model(
        config.get("pydantic").get("TextAnnotationen")
    )

    agent = Agent(
        model=getattr(import_module(_ai_model_module), _ai_model_name)(
            model_name=_ai_model_dict.get("name", "alias-large"),
            provider=getattr(import_module(_ai_provider_module), _ai_provider_name)(
                base_url=_ai_provider_dict.get(
                    "url", "https://api.helmholtz-blablador.fz-juelich.de/v1/"
                ),
                api_key=_ai_provider_dict.get("api_key", api_key)
                if _ai_provider_dict.get("api_key", api_key) is not None
                else api_key,
            ),
        ),
        system_prompt=config.get("prompt"),
        output_type=_pydantic_model,
    )
    return agent.run_sync(query)
