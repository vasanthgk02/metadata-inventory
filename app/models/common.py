from pydantic import BaseModel


class AcceptedResponse(BaseModel):
    message: str


class ErrorResponse(BaseModel):
    detail: str
