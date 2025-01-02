from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, create_model
from typing import Any, Dict, List, Optional

app = FastAPI()

# Route to dynamically generate a model based on user-provided fields
@app.post("/create-model/")
async def create_model_endpoint(model_name: str, fields: Dict[str, Dict[str, Any]]):
    """
    Create a dynamic Pydantic model based on user input.

    Args:
    - model_name: Name of the model to create.
    - fields: Dictionary containing field definitions. 
      Format: {"field_name": {"type": "str", "default": None, "description": "Some description"}}

    Returns:
    - JSON schema of the created model.
    """
    try:
        # Map string types to Python types
        type_mapping = {
            "str": str,
            "int": int,
            "float": float,
            "bool": bool,
            "list": list,
            "dict": dict,
        }

        # Prepare field definitions for the dynamic model
        model_fields = {
            field_name: (
                type_mapping[field_props["type"]],
                Field(
                    default=field_props.get("default"),
                    description=field_props.get("description", ""),
                ),
            )
            for field_name, field_props in fields.items()
        }

        # Create the dynamic model
        DynamicModel = create_model(model_name, **model_fields)

        # Return the model schema
        return {"model_name": model_name, "schema": DynamicModel.schema()}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# Example: Validate data using a dynamically created model
@app.post("/validate-data/")
async def validate_dynamic_data(
    model_name: str, fields: Dict[str, Dict[str, Any]], data: Dict[str, Any]
):
    """
    Validate incoming data against a dynamically created model.

    Args:
    - model_name: Name of the model to create.
    - fields: Field definitions for the model.
    - data: Data to validate.

    Returns:
    - Validated data.
    """
    try:
        # Create the dynamic model
        type_mapping = {
            "str": str,
            "int": int,
            "float": float,
            "bool": bool,
            "list": list,
            "dict": dict,
        }
        model_fields = {
            field_name: (
                type_mapping[field_props["type"]],
                Field(
                    default=field_props.get("default"),
                    description=field_props.get("description", ""),
                ),
            )
            for field_name, field_props in fields.items()
        }
        DynamicModel = create_model(model_name, **model_fields)

        # Validate data
        validated_data = DynamicModel(**data)
        return {"validated_data": validated_data.dict()}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
