# Docker Basics

## 1. Core Concepts

Docker lets you package an application and its dependencies into a lightweight, portable **container** that runs consistently across any environment.

- **Image**: A read-only template with instructions for creating a container (e.g., `python:3.11-slim`). Think of it as a snapshot or blueprint.
- **Container**: A runnable instance of an image — isolated, with its own filesystem, network, and process space.
- **Dockerfile**: A text file with instructions (`FROM`, `COPY`, `RUN`, `CMD`) used to build an image automatically.
- **Registry**: A storehouse for images (Docker Hub is the default public registry). You `push` images to and `pull` them from a registry.

> **Key idea**: An image is built in layers. Each `Dockerfile` instruction adds a layer, making images reusable and efficient.

## 2. Essential Commands & Workflow

```bash
# Build an image from a Dockerfile (in the current directory)
docker build -t myapp:1.0 .

# Run a container from the image
docker run -d -p 8080:80 --name myapp myapp:1.0

# List running containers
docker ps

# Stop and remove a container
docker stop myapp && docker rm myapp

# Remove an image
docker rmi myapp:1.0

# View logs from a container
docker logs myapp
```

**Quick workflow**: Write a `Dockerfile` → `docker build` to create an image → `docker run` to start a container → `docker push` to share it via a registry.
