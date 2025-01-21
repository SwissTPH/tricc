from setuptools import setup

setup(
    name="tricc-oo",
    version="1.1.25",
    author="DHU SwissTPH httu.admin@swisstph.ch",
    description="Python library that converts XLS to Fhir SDC ressource.",
    long_description="Python library that converts XLS to Fhir SDC ressource.",
    url="https://github.com/SwissTPH/tricc",
    keywords="xlsform, drawio, authoring",
    python_requires=">=3.8, <4",
    install_requires=[
        "lxml",
        "html2text",
        "pydantic",
        "babel",
        "xlsxwriter",
        "pandas",
        "polib",
        "StrEnum",
        "fhir.resources",
        "antlr4-python3-runtime",
        "antlr-ast",
        "antlr-tools",
        "bs4"   
    ],
    # extras_require={
    #    'test': ['pytest', 'coverage'],
    # },
    # package_data={
    #    'sample': ['example_data.csv'],
    # },
    # entry_points={
    #    'runners': [
    #        'sample=sample:main',
    #    ]
    # }
)
