# Set the base image to use, which is "mambaorg/micromamba:1.5.1"
FROM mambaorg/micromamba:1.5.1

# Create a named volume at "/opt/admet_ai/data" in the container to persist data across container runs
VOLUME /opt/admet_ai/data

# Switch to the root user to perform some installation tasks
USER root

# Install git, and wkhtmltopdf for PDF reports, then remove the apt cache to reduce image size
RUN apt-get update && \
    apt-get install -y --no-install-recommends git wkhtmltopdf && \
    rm -rf /var/lib/apt/lists/*

# Switch back to the non-root user specified in the "MAMBA_USER" environment variable
USER $MAMBA_USER

# Create a new conda environment named "base"
# Then, clean up the micromamba cache and other unnecessary files
RUN micromamba install -y -n base -c conda-forge python=3.10 xorg-libxrender && \
    micromamba clean --all --yes

# Install the CPU-only build of PyTorch first so pip does not pull the much larger CUDA build
RUN /opt/conda/bin/python -m pip install --no-cache-dir "torch==2.5.1" --index-url https://download.pytorch.org/whl/cpu

# Copy the current directory from the host to the container's "/opt/admet_ai" directory
COPY --chown=$MAMBA_USER:$MAMBA_USER . /opt/admet_ai

# Set the working directory to "/opt/admet_ai"
WORKDIR /opt/admet_ai

# Install the Python package in editable mode within the conda environment "base" previously created
RUN /opt/conda/bin/python -m pip install --no-cache-dir -e .[web]

# Expose port 5000 for the container to listen on
EXPOSE 5000

# Change the working directory to "/opt/admet_ai/admet_ai/web"
WORKDIR /opt/admet_ai/admet_ai/web

# Set CHEMXPLORE_SECRET_KEY at runtime (docker run -e CHEMXPLORE_SECRET_KEY=...) so sessions survive restarts.
# Predictions are kept in memory per process, so use one worker with several threads rather than more workers.
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "4", "--timeout", "300", "wsgi:build_app()"]
