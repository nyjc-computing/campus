# devcontainer-flask

Upstream devcontainer configuration for Flask-based Campus applications in the nyjc-computing organization.

## Usage

To use this configuration in your Flask project:

```bash
# Copy the devcontainer config to your project
cp -r devcontainer-flask/.devcontainer your-project/.devcontainer
cp devcontainer-flask/.gitignore your-project/.gitignore
```

Or if your project already has a `.devcontainer` folder, you can use the [Dev Containers: Add Dev Container Configuration...](https://code.visualstudio.com/docs/devcontainers/create-dev-container#_automatically-create-a-devcontainerjson-file) command in VS Code and select "From existing configuration".

## What's Included

### `.devcontainer/devcontainer.json`
- Python 3.11 base image
- VS Code Python extensions (Python, Pylance)
- Automatic post-create setup

### `.devcontainer/post-create.sh`
- Configures Git for fast-forward only pulls (`git config pull.ff true`)
- Installs [Poetry](https://python-poetry.org/) for dependency management
- Installs `poetry-plugin-shell` for enhanced shell integration
- Installs [GitHub CLI](https://cli.github.com/) (`gh`)
- Runs `poetry install` if `pyproject.toml` exists

### `.gitignore`
Comprehensive Python/Flask gitignore including:
- Standard Python artifacts (`__pycache__`, `*.pyc`, etc.)
- Virtual environments (`.venv`, `venv/`)
- **Sensitive files**: `.env`, `.claude/`, credentials, keys
- IDE configurations (VS Code, PyCharm, etc.)
- Development databases (`*.db`, `*.sqlite`)
- OS-specific files

## Project-Specific Overrides

Projects with additional requirements (e.g., database services) can extend this base configuration:

### Example: Adding PostgreSQL with Docker Compose

```json
{
	"name": "Python Flask DevContainer",
	"dockerComposeFile": "docker-compose.yml",
	"service": "app",
	"workspaceFolder": "/workspaces/${localWorkspaceFolderBasename}",
	// ... rest of config
}
```

See the `campus` project for a complete example with PostgreSQL and MongoDB services.

## Requirements

- [VS Code](https://code.visualstudio.com/) with [Dev Containers extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers)
- [Docker](https://www.docker.com/) or [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- A Flask project with `pyproject.toml` (Poetry)

## License

MIT
