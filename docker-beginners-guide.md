# Docker for Beginners: A Complete Getting Started Guide

> **Learn Docker from scratch** — no prior experience required. This guide covers everything from core concepts to running your first containerized application.

---

## Table of Contents

1. [What Is Docker?](#1-what-is-docker)
2. [Core Concepts](#2-core-concepts)
3. [Installing Docker](#3-installing-docker)
4. [Your First Container](#4-your-first-container)
5. [Essential Docker Commands](#5-essential-docker-commands)
6. [Working with Images](#6-working-with-images)
7. [Writing Your First Dockerfile](#7-writing-your-first-dockerfile)
8. [Managing Data & Networks](#8-managing-data--networks)
9. [Docker Compose](#9-docker-compose)
10. [Common Workflows](#10-common-workflows)
11. [Best Practices](#11-best-practices)
12. [Troubleshooting](#12-troubleshooting)
13. [Next Steps](#13-next-steps)

---

## 1. What Is Docker?

### The Problem Docker Solves

Before Docker, deploying applications was messy. You'd develop on your machine, then discover it "works on my machine" but fails in production. Dependencies conflict, OS versions differ, and environments are inconsistent.

**Docker** solves this by packaging your application and everything it needs to run into a **container** — a lightweight, portable, self-contained unit.

### Virtual Machines vs. Containers

| | Virtual Machine | Container |
|---|---|---|
| **Size** | Gigabytes | Megabytes |
| **Startup** | Minutes | Seconds |
| **OS** | Full guest OS per VM | Shares host OS kernel |
| **Overhead** | High (hypervisor) | Low (direct kernel access) |

Containers share the host operating system kernel but run in isolated user spaces. This makes them **fast**, **lightweight**, and **portable**.

### Why Use Docker?

- ✅ **Consistency** — "Works on my machine" → "Works everywhere"
- ✅ **Isolation** — Apps don't interfere with each other
- ✅ **Portability** — Run anywhere Docker is installed
- ✅ **Efficiency** — Higher density, lower resource usage
- ✅ **CI/CD** — Streamlined build, test, and deploy pipelines
- ✅ **Scalability** — Easy horizontal scaling

---

## 2. Core Concepts

### Image

A **Docker image** is a read-only template with instructions for creating a container. Think of it as a **blueprint** or **snapshot** of a filesystem.

- Images are built from a `Dockerfile`
- They contain your application code + dependencies + runtime
- Stored in layers (each instruction adds a layer)

### Container

A **container** is a runnable instance of an image. It's an isolated process with its own filesystem, network, and environment — but sharing the host kernel.

```
Image (blueprint) → Container (running instance)
```

### Dockerfile

A **Dockerfile** is a text file containing instructions for building a Docker image. Each line is a command (e.g., `FROM`, `RUN`, `COPY`, `CMD`).

### Registry

A **Docker registry** stores and distributes Docker images. The default public registry is **Docker Hub** (`hub.docker.com`), but you can also use private registries.

### Layer

Every instruction in a Dockerfile creates a **layer** — a read-only filesystem layer. Layers are cached and reused, making builds fast and images small.

### Volume

A **volume** is a persistent data store managed by Docker. Unlike container filesystems (which are ephemeral), volumes survive container deletion and can be shared between containers.

---

## 3. Installing Docker

### Windows & macOS

Download **Docker Desktop**:

- [Docker Desktop for Windows](https://desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.exe)
- [Docker Desktop for macOS (Intel)](https://desktop.docker.com/mac/main/amd64/Docker.dmg)
- [Docker Desktop for macOS (Apple Silicon)](https://desktop.docker.com/mac/main/arm64/Docker.dmg)

After installation, launch Docker Desktop and verify:

```bash
docker --version
docker run hello-world
```

### Linux (Ubuntu/Debian)

```bash
# Uninstall old versions
sudo apt-get remove docker docker-engine docker.io containerd runc

# Set up the repository
sudo apt-get update
sudo apt-get install \
    ca-certificates curl gnupg lsb-release

# Add Docker's official GPG key
sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
    | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg

# Add the repository
echo \
  "deb [arch $(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install
sudo apt-get update
sudo apt-get install docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Verify
docker --version
docker run hello-world
```

### Linux (Fedora/CentOS/RHEL)

```bash
sudo dnf -y install dnf-plugins-core
sudo dnf config-manager \
    --add-repo https://download.docker.com/linux/fedora/docker-ce.repo
sudo dnf install docker-ce docker-ce-cli containerd.io docker-compose-plugin
sudo systemctl --now enable --now docker
docker --version
```

### Post-Installation (Linux)

By default, Docker requires `sudo`. To run without `sudo`:

```bash
sudo usermod -aG docker $USER
# Log out and back in, or:
newgrp docker
```

---

## 4. Your First Container

Let's run your first Docker container — the classic `hello-world`:

```bash
docker run hello-world
```

**What happens:**

1. Docker checks if the `hello-world` image exists locally
2. If not, it downloads it from Docker Hub
3. Docker creates a new container from the image
4. The container runs and prints a message
5. The container exits

### Running an Interactive Container

Let's run an Ubuntu container interactively:

```bash
docker run -it ubuntu:latest bash
```

- `-i` — keep STDIN open (interactive)
- `-t` — allocate a pseudo-TTY (terminal)
- `ubuntu:latest` — the image name and tag
- `bash` — the command to run inside the container

You're now inside the Ubuntu container! Try:

```bash
whoami       # root
cat /etc/os-release  # Ubuntu details
exit         # leave the container
```

### Running a Web Server

```bash
docker run -d -p 8080:80 --name webserver nginx:latest
```

- `-d` — run in detached mode (in the background)
- `-p 8080:80` — map host port 8080 to container port 80
- `--name webserver` — give the container a name
- `nginx:latest` — use the latest Nginx image

Visit `http://localhost:8080` in your browser. You should see the Nginx welcome page.

To stop and remove it:

```bash
docker stop webserver
docker rm webserver
```

---

## 5. Essential Docker Commands

### Container Management

| Command | Description |
|---|---|
| `docker run [OPTIONS] IMAGE [COMMAND]` | Create and start a container |
| `docker ps` | List running containers |
| `docker ps -a` | List all containers (including stopped) |
| `docker start CONTAINER` | Start a stopped container |
| `docker stop CONTAINER` | Stop a running container |
| `docker restart CONTAINER` | Restart a container |
| `docker rm CONTAINER` | Remove a stopped container |
| `docker rm -f CONTAINER` | Force remove a running container |
| `docker logs CONTAINER` | View container logs |
| `docker exec -it CONTAINER COMMAND` | Run a command inside a running container |
| `docker inspect CONTAINER` | View detailed container info |

### Image Management

| Command | Description |
|---|---|
| `docker images` | List local images |
| `docker pull IMAGE` | Download an image without running it |
| `docker rmi IMAGE` | Remove an image |
| `docker image prune` | Remove unused images |
| `docker image prune -a` | Remove all unused images |
| `docker tag SOURCE[:TAG] TARGET[:TAG]` | Tag an image |

### System Commands

| Command | Description |
|---|---|
| `docker info` | Display system-wide information |
| `docker version` | Show Docker version |
| `docker system df` | Show disk usage |
| `docker system prune` | Remove all stopped containers, networks, and dangling images |
| `docker system prune -a` | Remove all unused data |

### Common `docker run` Options

```bash
docker run [OPTIONS] IMAGE [COMMAND] [ARG...]

# Key options:
-d              # Detached mode (run in background)
-p HOST:CONT    # Publish a container's port(s) to the host
-e KEY=VALUE    # Set environment variables
-v HOST:CONT    # Bind mount a volume
--name NAME     # Assign a name to the container
--rm            # Automatically remove the container when it exits
-it             # Interactive mode with a TTY
--network NAME  # Connect to a network
```

---

## 6. Working with Images

### Pulling Images

```bash
# Pull the latest Nginx image
docker pull nginx

# Pull a specific version
docker pull nginx:1.25

# Pull from a specific registry
docker pull registry.gitlab.com/mygroup/myapp:latest
```

### Searching for Images

```bash
docker search nginx
```

### Tagging Images

```bash
# Tag a local image
docker tag nginx:latest myname/nginx:v1

# Tag for pushing to a registry
docker tag myapp:latest mydockerhubuser/myapp:latest
```

### Building Images from a Dockerfile

```bash
# Build an image from a Dockerfile in the current directory
docker build -t myusername/myapp:1.0 .

# Build with a specific Dockerfile
docker build -f Dockerfile.dev -t myapp:dev .

# Build with build arguments
docker build --build-arg NODE_ENV=production -t myapp .
```

### Pushing Images to a Registry

```bash
# Log in to Docker Hub
docker login

# Tag your image
docker tag myapp:latest mydockerhubuser/myapp:latest

# Push
docker push mydockerhubuser/myapp:latest

# Log out
docker logout
```

---

## 7. Writing Your First Dockerfile

A **Dockerfile** is a script of instructions for building a Docker image. Let's create one for a simple Python Flask app.

### Project Structure

```
my-flask-app/
├── app.py
├── requirements.txt
└── Dockerfile
```

### app.py

```python
from flask import Flask

app = Flask(__name__)

@app.route("/")
def hello():
    return "Hello from Docker!"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
```

### requirements.txt

```
Flask==3.0.0
```

### Dockerfile

```dockerfile
# Use an official Python runtime as the base image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Copy requirements first (for better caching)
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Expose the port the app runs on
EXPOSE 5000

# Run the application
CMD ["python", "app.py"]
```

### Building and Running

```bash
# Build the image
docker build -t my-flask-app .

# Run the container
docker run -d -p 5000:5000 --name flask-app my-flask-app

# Test it
curl http://localhost:5000
# Output: Hello from Docker!
```

### Dockerfile Instructions Explained

| Instruction | Description |
|---|---|
| `FROM` | Sets the base image |
| `WORKDIR` | Sets the working directory |
| `COPY` | Copies files from the host to the container |
| `ADD` | Like COPY but also handles URLs and tar extraction |
| `RUN` | Executes a command and creates a new layer |
| `CMD` | Provides default command to run when container starts |
| `ENTRYPOINT` | Configures the container to run as an executable |
| `ENV` | Sets environment variables |
| `EXPOSE` | Informs Docker that the container listens on a port |
| `ARG` | Defines a build-time variable |
| `USER` | Sets the user to run the container |
| `VOLUME` | Creates a mount point for persistent data |
| `LABEL` | Adds metadata to the image |

### Multi-Stage Builds

Multi-stage builds let you reduce image size by using multiple `FROM` statements:

```dockerfile
# Build stage
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci --only=production
COPY . .
RUN npm run build

# Production stage
FROM node:20-alpine AS runtime
WORKDIR /app
COPY --from=builder /app/dist ./dist
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./package.json
EXPOSE 3000
CMD ["node", "dist/index.js"]
```

---

## 8. Managing Data & Networks

### Volumes

Volumes are the preferred way to persist data generated by containers.

```bash
# Create a volume
docker volume create mydata

# Use a volume in a container
docker run -d --name db -v mydata:/var/lib/mysql mysql:8.0

# List volumes
docker volume ls

# Inspect a volume
docker volume inspect mydata

# Remove a volume
docker volume rm mydata

# Remove all unused volumes
docker volume prune
```

### Bind Mounts

Bind mounts link a host directory to a container directory:

```bash
# Mount a host directory
docker run -d --name webserver -v /host/path:/usr/share/nginx/html nginx

# Mount in read-only mode
docker run -d --name webserver -v /host/path:/usr/share/nginx/html:ro nginx
```

### Networks

```bash
# List networks
docker network ls

# Create a network
docker network create my-network

# Run containers on a custom network
docker run -d --name app1 --network my-network nginx
docker run -d --name app2 --network my-network nginx

# Connect a container to a network
docker network connect my-network existing-container

# Disconnect
docker network disconnect my-network container-name

# Remove a network
docker network rm my-network
```

### Network Drivers

| Driver | Description |
|---|---|
| `bridge` | Default. Containers on the same host communicate via IP |
| `host` | Container uses the host's network stack directly |
| `none` | No networking |
| `overlay` | Connects multiple Docker hosts (Swarm mode) |

---

## 9. Docker Compose

**Docker Compose** is a tool for defining and running multi-container Docker applications.

### Installation

Docker Compose is included with Docker Desktop. On Linux, install the plugin:

```bash
sudo apt-get install docker-compose-plugin
```

### docker-compose.yml

Create a `docker-compose.yml` file:

```yaml
version: "3.9"

services:
  web:
    build: .
    ports:
      - "5000:5000"
    environment:
      - FLASK_ENV=development
    volumes:
      - .:/app
    depends_on:
      - db

  db:
    image: postgres:16
    environment:
      POSTGRES_USER: myuser
      POSTGRES_PASSWORD: mypassword
      POSTGRES_DB: mydb
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  redis:
    image: redis:7-alpine

volumes:
  postgres_data:
```

### Compose Commands

```bash
# Start all services
docker compose up

# Start in detached mode
docker compose up -d

# Build images
docker compose build

# Stop services
docker compose stop

# Stop and remove containers, networks, volumes
docker compose down

# View logs
docker compose logs

# Run a one-off command
docker compose run web python manage.py migrate

# Scale a service
docker compose up --scale web=3
```

---

## 10. Common Workflows

### Workflow 1: Local Development

```bash
# 1. Write your Dockerfile
# 2. Build the image
docker build -t myapp .

# 3. Run with live reload (bind mount)
docker run -d -p 3000:3000 -v $(pwd):/app --name myapp-dev myapp

# 4. Make code changes — they reflect immediately
# 5. When done, stop and remove
docker stop myapp-dev && docker rm myapp-dev
```

### Workflow 2: Testing

```bash
# Build and run tests in an isolated container
docker build -t myapp:test .
docker run --rm myapp:test npm test

# Or use a separate Dockerfile for testing
docker build -f Dockerfile.test -t myapp:test .
docker run --rm myapp:test
```

### Workflow 3: Production Deployment

```bash
# 1. Build a production image
docker build -t myregistry.com/myapp:v1.0.0 .

# 2. Push to registry
docker push myregistry.com/myapp:v1.0.0

# 3. On the server, pull and run
docker pull myregistry.com/myapp:v1.0.0
docker run -d -p 80:80 --name myapp \
  --restart unless-stopped \
  myregistry.com/myapp:v1.0.0
```

### Useful Development Tips

```bash
# View real-time resource usage
docker stats

# Follow container logs
docker logs -f mycontainer

# Copy a file from a container to the host
docker cp mycontainer:/app/config.json ./config.json

# Copy a file from the host to a container
docker cp ./local-file.txt mycontainer:/tmp/

# Export a container's filesystem as a tar
docker export mycontainer > container.tar

# Import a tar as an image
docker import container.tar myimage:latest
```

---

## 11. Best Practices

### Image Best Practices

1. **Use official base images** — They're maintained and secure.
2. **Choose minimal base images** — `alpine` or `slim` variants reduce size.
3. **Minimize layers** — Combine related `RUN` commands with `&&`.
4. **Leverage build cache** — Put rarely-changing instructions first.
5. **Use `.dockerignore`** — Exclude files that shouldn't be in the image.

### .dockerignore Example

```
node_modules
npm-debug.log
.git
.gitignore
.env
Dockerfile
.dockerignore
README.md
*.md
tests/
```

### Security Best Practices

1. **Don't run as root** — Use a non-root user.
2. **Scan images** — Use tools like `docker scan` or Trivy.
3. **Keep images updated** — Regularly rebuild with latest base images.
4. **Use specific tags** — Avoid `latest` in production.
5. **Minimize attack surface** — Remove unnecessary tools and packages.

```dockerfile
# Run as non-root
RUN groupadd -r appuser && useradd -r -g appuser appuser
USER appuser
```

### Resource Management

```bash
# Limit CPU and memory
docker run -d --name myapp \
  --cpus="1.5" \
  --memory="512m" \
  --memory-swap="1g" \
  myapp:latest

# Set restart policies
docker run -d --restart=always myapp:latest
```

### Restart Policies

| Policy | Description |
|---|---|
| `no` | Don't restart (default) |
| `on-failure[:max-retries]` | Restart on failure |
| `unless-stopped` | Restart unless explicitly stopped |
| `always` | Always restart |

---

## 12. Troubleshooting

### Common Issues

#### "Cannot connect to the Docker daemon"

```bash
# Start the Docker daemon
sudo systemctl start docker
sudo systemctl enable docker

# Or on macOS/Windows, start Docker Desktop
```

#### "Port is already in use"

```bash
# Find what's using the port
sudo lsof -i :8080
# or
sudo netstat -tulpn | grep 8080

# Kill the process
sudo kill -9 PID
```

#### "No space left on device"

```bash
# Clean up unused data
docker system prune -a

# Remove all stopped containers
docker container prune

# Remove all unused volumes
docker volume prune

# Check disk usage
docker system df
```

#### "Permission denied" (Linux)

```bash
# Add your user to the docker group
sudo usermod -aG docker $USER
# Log out and log back in
```

#### Image build fails

```bash
# Build with no cache
docker build --no-cache -t myapp .

# Build with verbose output
docker build --progress=plain -t myapp .
```

### Debugging Commands

```bash
# Check Docker info
docker info

# Check Docker version
docker version

# View running processes
docker top mycontainer

# View container's filesystem changes
docker diff mycontainer

# View container's environment variables
docker exec mycontainer env

# Inspect a container (JSON details)
docker inspect mycontainer

# Inspect an image
docker image inspect myimage
```

---

## 13. Next Steps

### Learning Resources

- **[Docker Documentation](https://docs.docker.com/)** — Official docs
- **[Docker Curriculum](https://docker-curriculum.com/)** — Free comprehensive tutorial
- **[Play with Docker](https://labs.play-with-docker.com/)** — Browser-based playground
- **[Dockerfile Reference](https://docs.docker.com/engine/reference/builder/)** — Official instruction reference

### Advanced Topics to Explore

1. **Docker Swarm** — Native clustering and orchestration
2. **Kubernetes** — Container orchestration at scale
3. **Docker Security** — Image signing, secrets management
4. **Multi-architecture builds** — Build for ARM, x86, etc.
5. **CI/CD Integration** — GitHub Actions, GitLab CI, Jenkins
6. **Container registries** — Harbor, AWS ECR, Google GCR
7. **Monitoring & logging** — Prometheus, Grafana, ELK stack

### Quick Reference Cheat Sheet

```bash
# Run a container
docker run -it --rm -p 8080:80 nginx

# Build an image
docker build -t myapp .

# List containers
docker ps -a

# Stop a container
docker stop myapp

# Remove a container
docker rm myapp

# Remove an image
docker rmi myapp

# View logs
docker logs -f myapp

# Execute a command in a running container
docker exec -it myapp bash

# Clean up everything
docker system prune -a

# Compose up
docker compose up -d

# Compose down
docker compose down
```

---

## Quick Recap

| Concept | What It Is |
|---|---|
| **Image** | A read-only template (blueprint) |
| **Container** | A running instance of an image |
| **Dockerfile** | Instructions to build an image |
| **Registry** | Stores and shares images (Docker Hub) |
| **Volume** | Persistent data storage |
| **Network** | Connects containers to each other |
| **Compose** | Multi-container application management |

---

> **💡 Tip:** Start small. Run a single `nginx` container, then try building your own image. Master the basics before moving to Compose and orchestration.

Happy containerizing! 🐳
