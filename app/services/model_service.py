import os
import sys
import math
import tempfile
from pathlib import Path
from typing import Dict, Optional, Tuple, List, Any
import numpy as np
import trimesh

# Ensure OrthoCAD_Repo/src is importable even if not pip-installed yet
ORTHOCAD_SRC = Path(__file__).resolve().parents[3] / "OrthoCAD_Repo" / "src"
if ORTHOCAD_SRC.exists() and str(ORTHOCAD_SRC) not in sys.path:
    sys.path.insert(0, str(ORTHOCAD_SRC))

from orthocad.advanced_reconstruction import (
    extract_outer_contour,
    extract_features_by_difference,
    close_shape_with_boundary,
)
from orthocad.extrusion import extrude_shape
from orthocad.boolean_ops import union_meshes, intersection_meshes, subtract_meshes


def generate_3d_mesh_from_views(
    top_image_path: Optional[str] = None,
    front_image_path: Optional[str] = None,
    side_image_path: Optional[str] = None,
    extract_internal_features: bool = True,
) -> Tuple[List[List[float]], List[List[int]], List[List[float]], List[str]]:
    """
    Headless 3D reconstruction pipeline using OrthoCAD's visual hull + feature subtraction engine.

    Args:
        top_image_path: File path to the Top (XY) view image.
        front_image_path: File path to the Front (XZ) view image.
        side_image_path: File path to the Side (YZ) view image.
        extract_internal_features: Whether to extract internal lines/holes and boolean-subtract them.

    Returns:
        Tuple of (vertices, faces, normals, views_used)
    """
    plane_to_path = {
        "XY": top_image_path,
        "XZ": front_image_path,
        "YZ": side_image_path,
    }

    outer_meshes = []
    view_data: Dict[str, Dict[str, Any]] = {}
    views_used: List[str] = []

    for plane, path in plane_to_path.items():
        if not path or not os.path.exists(path):
            continue

        pts_3d, pts_2d = extract_outer_contour(path, plane)
        if pts_3d:
            view_data[plane] = {
                "path": path,
                "outer_2d": pts_2d,
            }
            shape_data = {
                "type": "polygon",
                "plane": plane,
                "points": pts_3d,
                "closed": True,
            }
            verts, tris, norms = extrude_shape(shape_data, -10.0, 10.0, 1.0, 1.0)
            if verts and tris:
                outer_meshes.append((verts, tris, norms))
                views_used.append(plane)

    if not outer_meshes:
        raise ValueError("Could not extract any valid 2D outer contours from the provided view images.")

    # 1. Intersect main extruded silhouettes to form the Visual Hull base object
    final_mesh = outer_meshes[0]
    for i in range(1, len(outer_meshes)):
        result = intersection_meshes(final_mesh, outer_meshes[i])
        if result and len(result[0]) > 0:
            final_mesh = result

    # 2. Internal Feature Extraction & Boolean Subtraction
    if extract_internal_features and view_data:
        all_polylines = {}
        for plane, data in view_data.items():
            polys = extract_features_by_difference(
                data["path"], final_mesh, plane, data["outer_2d"]
            )
            all_polylines[plane] = polys

        profiles = []
        depth_lines = []

        for plane, polys in all_polylines.items():
            outer_2d = view_data[plane]["outer_2d"]
            for poly in polys:
                raw_xs = [p[0] for p in poly]
                raw_ys = [p[1] for p in poly]
                raw_w = max(raw_xs) - min(raw_xs)
                raw_h = max(raw_ys) - min(raw_ys)

                closed_poly = close_shape_with_boundary(poly, outer_2d)

                xs = [p[0] for p in closed_poly]
                ys = [p[1] for p in closed_poly]
                w = max(xs) - min(xs)
                h = max(ys) - min(ys)

                dist_ends = math.hypot(
                    closed_poly[0][0] - closed_poly[-1][0],
                    closed_poly[0][1] - closed_poly[-1][1],
                )
                is_closed = dist_ends < 0.05 and len(closed_poly) >= 4

                if raw_w > 0.025 and raw_h > 0.025 and w > 0.04 and h > 0.04 and is_closed:
                    profiles.append(
                        {
                            "plane": plane,
                            "poly": closed_poly,
                            "xs": (min(raw_xs), max(raw_xs)),
                            "ys": (min(raw_ys), max(raw_ys)),
                        }
                    )
                else:
                    depth_lines.append(
                        {
                            "plane": plane,
                            "poly": poly,
                            "xs": (min(raw_xs), max(raw_xs)),
                            "ys": (min(raw_ys), max(raw_ys)),
                        }
                    )

        negative_meshes_by_view = []
        for prof in profiles:
            plane = prof["plane"]
            poly = prof["poly"]

            points_3d = []
            for pt in poly:
                nx = pt[0] * 20 - 10
                ny = (1.0 - pt[1]) * 20 - 10
                if plane == "XY":
                    points_3d.append([nx, ny, 0.0])
                elif plane == "XZ":
                    points_3d.append([nx, 0.0, ny])
                elif plane == "YZ":
                    points_3d.append([0.0, nx, ny])

            shape_data = {
                "type": "polygon",
                "plane": plane,
                "points": points_3d,
                "closed": True,
            }

            extrude_min = -12.0
            extrude_max = 12.0
            matched_depths = []

            for dl in depth_lines:
                dl_plane = dl["plane"]
                dl_w = dl["xs"][1] - dl["xs"][0]
                dl_h = dl["ys"][1] - dl["ys"][0]
                is_horiz = dl_h < 0.04 and dl_w > 0.04
                is_vert = dl_w < 0.04 and dl_h > 0.04

                if plane == "XZ" and dl_plane == "XY" and is_horiz:
                    if max(prof["xs"][0], dl["xs"][0]) < min(prof["xs"][1], dl["xs"][1]) + 0.05:
                        depth_y = (1.0 - (dl["ys"][0] + dl["ys"][1]) / 2.0) * 20 - 10
                        matched_depths.append(depth_y)
                elif plane == "XZ" and dl_plane == "YZ" and is_vert:
                    if max(prof["ys"][0], dl["ys"][0]) < min(prof["ys"][1], dl["ys"][1]) + 0.05:
                        depth_y = ((dl["xs"][0] + dl["xs"][1]) / 2.0) * 20 - 10
                        matched_depths.append(depth_y)
                elif plane == "XY" and dl_plane == "XZ" and is_horiz:
                    if max(prof["xs"][0], dl["xs"][0]) < min(prof["xs"][1], dl["xs"][1]) + 0.05:
                        depth_z = (1.0 - (dl["ys"][0] + dl["ys"][1]) / 2.0) * 20 - 10
                        matched_depths.append(depth_z)
                elif plane == "XY" and dl_plane == "YZ" and is_horiz:
                    prof_yw = (1.0 - prof["ys"][1], 1.0 - prof["ys"][0])
                    if max(prof_yw[0], dl["xs"][0]) < min(prof_yw[1], dl["xs"][1]) + 0.05:
                        depth_z = (1.0 - (dl["ys"][0] + dl["ys"][1]) / 2.0) * 20 - 10
                        matched_depths.append(depth_z)
                elif plane == "YZ" and dl_plane == "XZ" and is_vert:
                    if max(prof["ys"][0], dl["ys"][0]) < min(prof["ys"][1], dl["ys"][1]) + 0.05:
                        depth_x = ((dl["xs"][0] + dl["xs"][1]) / 2.0) * 20 - 10
                        matched_depths.append(depth_x)
                elif plane == "YZ" and dl_plane == "XY" and is_vert:
                    dl_yw = (1.0 - dl["ys"][1], 1.0 - dl["ys"][0])
                    if max(prof["xs"][0], dl_yw[0]) < min(prof["xs"][1], dl_yw[1]) + 0.05:
                        depth_x = ((dl["xs"][0] + dl["xs"][1]) / 2.0) * 20 - 10
                        matched_depths.append(depth_x)

            unique_depths = []
            for d in sorted(matched_depths):
                if not unique_depths or abs(d - unique_depths[-1]) > 0.5:
                    unique_depths.append(d)

            if len(unique_depths) >= 2:
                extrude_min = unique_depths[0]
                extrude_max = unique_depths[-1]
            elif len(unique_depths) == 1:
                if unique_depths[0] > 0:
                    extrude_min = unique_depths[0]
                else:
                    extrude_max = unique_depths[0]

            neg_mesh = extrude_shape(shape_data, extrude_min, extrude_max, 1.0, 1.0)
            if neg_mesh and len(neg_mesh[0]) > 0:
                negative_meshes_by_view.append(neg_mesh)

        if negative_meshes_by_view:
            final_neg_mesh = negative_meshes_by_view[0]
            for i in range(1, len(negative_meshes_by_view)):
                result = union_meshes(final_neg_mesh, negative_meshes_by_view[i])
                if result and len(result[0]) > 0:
                    final_neg_mesh = result

            if final_neg_mesh and len(final_neg_mesh[0]) > 0:
                result = subtract_meshes(final_mesh, final_neg_mesh)
                if result and len(result[0]) > 0:
                    final_mesh = result

    verts_raw, faces_raw, norms_raw = final_mesh
    vertices = np.asarray(verts_raw, dtype=float).tolist()
    faces = np.asarray(faces_raw, dtype=int).tolist()
    normals = np.asarray(norms_raw, dtype=float).tolist()

    return vertices, faces, normals, views_used


def export_mesh_bytes(
    vertices: List[List[float]],
    faces: List[List[int]],
    normals: Optional[List[List[float]]] = None,
    file_format: str = "stl",
) -> Tuple[bytes, bool]:
    """
    Converts raw vertices and faces into a trimesh object and exports it to bytes
    in the requested 3D format ('stl', 'obj', 'glb', 'ply', 'off').
    """
    t_mesh = trimesh.Trimesh(
        vertices=np.asarray(vertices, dtype=float),
        faces=np.asarray(faces, dtype=int),
        vertex_normals=np.asarray(normals, dtype=float) if normals else None,
        process=True,
    )
    exported = t_mesh.export(file_type=file_format.lower())
    if isinstance(exported, str):
        exported = exported.encode("utf-8")
    return exported, bool(t_mesh.is_watertight)
