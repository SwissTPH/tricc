from setuptools import setup
import os

with open(os.path.join(os.path.dirname(__file__), 'README.md')) as readme:
    README = readme.read()


setup(
    name='tricc-oo',
    version='1.0.2',
    author='DHU SwissTPH httu.admin@swisstph.ch',
    description='Python library that converts XLS to Fhir SDC ressource.',
    # other arguments omitted
    long_description=README,
    long_description_content_type='text/markdown',
    url='https://github.com/SwissTPH/tricc',
    keywords='xlsform, drawio, authoring',
    python_requires='>=3.8, <4',
    install_requires=[
        "lxml",
        "html2text",
        "pydantic<2",
        "babel",
        "xlsxwriter",
        "pandas",
        "polib",
        "StrEnum",
        ],
    #extras_require={
    #    'test': ['pytest', 'coverage'],
    #},
    #package_data={
    #    'sample': ['example_data.csv'],
    #},
    #entry_points={
    #    'runners': [
    #        'sample=sample:main',
    #    ]
    #}
)
