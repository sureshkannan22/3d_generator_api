import os
import shutil
import tempfile
from typing import Optional, Literal
from fastapi import APIRouter, UploadFile, File, Query, HTTPException
from fastapi.responses import Response

from app.services.model_service import generate_3d_mesh_from_views, export_mesh_bytes

router = APIRouter(prefix="/generate", tags=["3D Model Generation (OrthoCAD)"])

MIME_TYPES = {
    "stl": "model/stl",
    "obj": "model/obj",
    "glb": "model/gltf-binary",
    "ply": "application/octet-stream",
}


def _save_upload_to_temp(upload: Optional[UploadFile], temp_dir: str, prefix: str) -> Optional[str]:
    if upload is None or not upload.filename:
        return None
    ext = os.path.splitext(upload.filename)[1] or ".png"
    dest_path = os.path.join(temp_dir, f"{prefix}{ext}")
    with open(dest_path, "wb") as f:
        shutil.copyfileobj(upload.file, f)
    return dest_path


@router.post(
    "/from-views",
    summary="Generate a 3D model from Top, Front, and Side 2D orthographic view images",
)
def generate_3d_from_views_endpoint(
    top_view: Optional[UploadFile] = File(None, description="Top view image (XY plane)"),
    front_view: Optional[UploadFile] = File(None, description="Front view image (XZ plane)"),
    side_view: Optional[UploadFile] = File(None, description="Side view image (YZ plane)"),
    output_format: Literal["stl", "obj", "glb", "ply", "json"] = Query(
        "stl",
        description="Output 3D model format: 'stl', 'obj', 'glb', 'ply' (file download), or 'json' (raw vertices/faces/normals)",
    ),
    extract_features: bool = Query(
        True,
        description="Extract internal features/holes and boolean-subtract them from the visual hull",
    ),
):
    """
    Upload up to 3 orthographic view images (**Top / XY**, **Front / XZ**, **Side / YZ**)
    and reconstruct a 3D solid mesh using OrthoCAD's visual hull + feature subtraction engine.
    """
    if not any([top_view, front_view, side_view]):
        raise HTTPException(
            status_code=400,
            detail="At least one view image (top_view, front_view, or side_view) must be provided.",
        )

    temp_dir = tempfile.mkdtemp(prefix="orthocad_views_")
    try:
        top_path = _save_upload_to_temp(top_view, temp_dir, "top_XY")
        front_path = _save_upload_to_temp(front_view, temp_dir, "front_XZ")
        side_path = _save_upload_to_temp(side_view, temp_dir, "side_YZ")

        try:
            vertices, faces, normals, views_used = generate_3d_mesh_from_views(
                top_image_path=top_path,
                front_image_path=front_path,
                side_image_path=side_path,
                extract_internal_features=extract_features,
            )
        except ValueError as ve:
            raise HTTPException(status_code=422, detail=str(ve))
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"3D reconstruction failed: {str(e)}",
            )

        fmt = output_format.lower()
        if fmt == "json":
            _, is_watertight = export_mesh_bytes(vertices, faces, normals, file_format="stl")
            return {
                "message": "Successfully generated 3D model from orthographic views.",
                "stats": {
                    "vertex_count": len(vertices),
                    "face_count": len(faces),
                    "is_watertight": is_watertight,
                    "views_used": views_used,
                },
                "vertices": vertices,
                "faces": faces,
                "normals": normals,
            }

        model_bytes, is_watertight = export_mesh_bytes(
            vertices, faces, normals, file_format=fmt
        )
        filename = f"generated_model.{fmt}"
        media_type = MIME_TYPES.get(fmt, "application/octet-stream")

        return Response(
            content=model_bytes,
            media_type=media_type,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "X-Vertex-Count": str(len(vertices)),
                "X-Face-Count": str(len(faces)),
                "X-Is-Watertight": str(is_watertight),
                "X-Views-Used": ",".join(views_used),
            },
        )
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
