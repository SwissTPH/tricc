FROM python:3.10-bookworm

WORKDIR /usr/src/app

COPY locales/ ./locales/
COPY tricc_oo/ ./tricc_oo/
COPY pyproject.toml pyproject.toml
COPY tests/build.py build.py

RUN pip install .

ENTRYPOINT [ "python", "/usr/src/app/build.py" ]
