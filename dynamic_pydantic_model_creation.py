from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, create_model
from typing import Any, Dict, Optional

app = FastAPI(
    title="Dynamic Pydantic Model API",
    description="""
This API allows you to **dynamically define and validate Pydantic models** at runtime.  
It exposes two main endpoints:
- `/create-model/` → Dynamically generate and inspect a model schema.
- `/validate-data/` → Validate JSON payloads against a dynamically created model.
""",
    version="1.0.0"
)

# Supported type mapping between string type names and Python types
TYPE_MAPPING = {
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "list": list,
    "dict": dict,
}


class ModelDefinition(BaseModel):
    """
    Represents the structure required to define a dynamic Pydantic model.

    Attributes:
        model_name (str): The name of the model to be created dynamically.
        fields (dict): A mapping of field names to their configuration.
            Example:
            {
                "username": {"type": "str", "default": None, "description": "User's name"},
                "age": {"type": "int", "default": 18, "description": "User's age"}
            }
    """
    model_name: str
    fields: Dict[str, Dict[str, Any]]


class ValidationRequest(ModelDefinition):
    """
    Request model for validating data against a dynamically generated model.

    Inherits:
        - model_name
        - fields

    Attributes:
        data (dict): The data payload to validate against the generated model.
    """
    data: Dict[str, Any]


def build_dynamic_model(model_name: str, fields: Dict[str, Dict[str, Any]]):
    """
    Dynamically constructs a Pydantic model class from user-defined field specifications.

    Args:
        model_name (str): The name of the model to be created.
        fields (dict): Field definitions, where keys are field names and values include:
            - type (str): The data type (must be one of TYPE_MAPPING).
            - default (Any, optional): Default value for the field.
            - description (str, optional): Description of the field.

    Returns:
        pydantic.BaseModel: A dynamically created Pydantic model class.

    Raises:
        HTTPException: If a provided type is not supported.
    """
    model_fields = {}
    for field_name, props in fields.items():
        field_type_str = props.get("type")

        if field_type_str not in TYPE_MAPPING:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported type '{field_type_str}' for field '{field_name}'"
            )

        py_type = TYPE_MAPPING[field_type_str]
        default = props.get("default")

        # Mark field as Optional if default is None
        if default is None:
            py_type = Optional[py_type]

        # Add field definition
        model_fields[field_name] = (
            py_type,
            Field(
                default=default,
                description=props.get("description", "")
            ),
        )

    return create_model(model_name, **model_fields)


@app.post(
    "/create-model/",
    summary="Create a dynamic Pydantic model",
    response_description="The schema of the dynamically created model."
)
async def create_model_endpoint(definition: ModelDefinition):
    """
    Generate a Pydantic model based on user-provided field definitions.

    This endpoint allows clients to inspect the generated model's JSON schema
    before using it for validation.

    Args:
        definition (ModelDefinition): Object containing `model_name` and `fields`.

    Returns:
        dict: A dictionary containing:
            - `model_name` (str): The name of the created model.
            - `schema` (dict): JSON schema representation of the model.
    """
    DynamicModel = build_dynamic_model(definition.model_name, definition.fields)
    return {"model_name": definition.model_name, "schema": DynamicModel.schema()}


@app.post(
    "/validate-data/",
    summary="Validate data against a dynamic model",
    response_description="The validated and parsed data."
)
async def validate_dynamic_data(request: ValidationRequest):
    """
    Validate JSON payload against a dynamically created Pydantic model.

    This endpoint:
    1. Creates a Pydantic model dynamically using the provided `model_name` and `fields`.
    2. Validates the `data` payload against that model.
    3. Returns the validated data in its parsed form.

    Args:
        request (ValidationRequest): Includes `model_name`, `fields`, and `data`.

    Returns:
        dict: A dictionary with a single key `validated_data`, containing the parsed and validated data.

    Raises:
        HTTPException: If validation fails or field definitions are invalid.
    """
    DynamicModel = build_dynamic_model(request.model_name, request.fields)
    validated = DynamicModel(**request.data)
    return {"validated_data": validated.dict()}
