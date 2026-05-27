# Gemini Project Context: xcorecli

`xcorecli` is a comprehensive Command Line Interface (CLI) tool designed to manage the `xcore` ecosystem. It facilitates project initialization, service monitoring, plugin lifecycle management, configuration handling, worker orchestration, and database migrations.

## 🚀 Quick Start

### Installation
The project uses `poetry` for dependency management.
```bash
make install
```

### Development
Run the application with auto-reload (using Uvicorn):
```bash
make dev
```

### Testing & Quality
```bash
make test        # Run pytest
make lint-fix    # Auto-format and lint code (black, isort, autopep8)
make lint-check  # Check linting without modifying files
```

### Core CLI Commands
The CLI is accessible via `xcli/main.py`. Key commands include:
- `init`: Generate `integration.yaml` for a new xcore project.
- `health`: Global health-check of all xcore services.
- `services`: Show status of all xcore services.
- `config`: Manage project configurations.
- `plugin`: Plugin management (install, local, marketplace, runtime, security, update).
- `sandbox`: Sandbox management for plugins.
- `worker`: Worker orchestration.
- `manager`: Core project management tasks.
- `migration`: Database migration management (Alembic).

## 🛠 Technology Stack
- **Language:** Python 3.12+
- **CLI Framework:** [Typer](https://typer.tiangolo.com/) & [Rich](https://rich.readthedocs.io/)
- **Database:** SQLAlchemy (Core/Async), Alembic (Migrations)
- **Web/API:** FastAPI, Uvicorn
- **Task Queue:** Celery / XWorker
- **Configuration:** YAML (`integration.yaml`)
- **Build System:** Poetry, UV
- **Documentation:** MkDocs

## 📂 Project Structure
- `xcli/`: Core CLI package.
  - `main.py`: Main entry point and command registration.
  - `config/`: Configuration management logic.
  - `init/`: Project initialization wizards and upgrade paths.
  - `manager/`: High-level project management logic.
  - `marketplace/`: Interaction with the xcore plugin marketplace.
  - `migrations/`: Database migration wrappers.
  - `plugin/`: Comprehensive plugin management (install, security, update).
  - `sandbox/`: Plugin sandboxing logic.
  - `worker/`: Worker and Celery integration.
- `docs/`: Project documentation (MkDocs).
- `integration.yaml`: Central configuration file for xcore projects.
- `makefile`: Automation for build, test, and dev tasks.

## 📝 Development Conventions
- **Modular Subcommands:** Each major CLI feature should reside in its own subpackage under `xcli/` with a `cli.py` for command registration.
- **Rich Output:** Use `rich` for all terminal output (Panels, Tables, Progress bars).
- **Configuration-First:** Most behaviors are driven by `integration.yaml`. Always validate against the schema when making changes.
- **Service Orientation:** The CLI often interacts with a `ServiceContainer` from `xcore`.
- **Linting:** Ensure all code passes `make lint-check` before committing. Use `make lint-fix` for automatic formatting.
