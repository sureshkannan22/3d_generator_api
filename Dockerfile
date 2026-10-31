FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /workspace

# System dependencies required by OpenCV / SciPy / Manifold3D / psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libgl1 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Copy OrthoCAD_Repo and install it without GUI dependencies (PyQt5/PyOpenGL)
COPY OrthoCAD_Repo /workspace/OrthoCAD_Repo
RUN pip install --no-cache-dir --no-deps -e /workspace/OrthoCAD_Repo

# Install FastAPI backend dependencies (excluding the -e ../OrthoCAD_Repo line since it's already installed)
COPY 3d_generator_project/requirements.txt /workspace/3d_generator_project/requirements.txt
RUN grep -v "^-e" /workspace/3d_generator_project/requirements.txt > /tmp/requirements.docker.txt && \
    pip install --no-cache-dir -r /tmp/requirements.docker.txt

# Copy backend source code
COPY 3d_generator_project /workspace/3d_generator_project

WORKDIR /workspace/3d_generator_project

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
