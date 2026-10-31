# app/schemas/3d_schema.py
from pydantic import BaseModel, Field
from typing import List, Optional, Literal

class MeshStats(BaseModel):
    vertex_count: int
    face_count: int
    is_watertight: bool
    views_used: List[str]

class MeshJSONResponse(BaseModel):
    message: str
    stats: MeshStats
    vertices: List[List[float]] = Field(..., description="List of [x, y, z] vertex coordinates")
    faces: List[List[int]] = Field(..., description="List of [v0, v1, v2] triangle vertex indices")
    normals: List[List[float]] = Field(..., description="List of [nx, ny, nz] vertex normals")
