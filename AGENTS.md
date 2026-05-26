# TRICC Project - Cline Rules

## Project Overview

TRICC (Transformable Rule-based Interactive Clinical Calculator) is a Python library that converts Clinical Decision Support System (CDSS) Level 2 specifications into Level 3 implementations. It processes visual flowcharts created in draw.io and converts them into various output formats like XLSForm, CHT, OpenMRS, FHIR, and HTML.

## Key Technologies

- **Language**: Python 3.8+
- **Core Dependencies**: lxml, pydantic, pandas, xlsxwriter, antlr4
- **Code Style**: PEP 8, max line length 120 (see .flake8)
- **Architecture**: Strategy pattern for input/output processing
- **Models**: Pydantic-based data models with custom types

## Project Structure

```
tricc_oo/
├── converters/      # Format conversion logic (drawio→tricc, tricc→outputs)
├── models/          # Pydantic data models (nodes, edges, operations)
├── parsers/         # XML parsing for draw.io files
├── serializers/     # Output format serialization
├── strategies/      # Input/output strategy implementations
├── tools/           # Draw.io templates and utilities
└── visitors/        # Graph traversal and processing
tests/               # Test suite and build scripts
docs/                # MkDocs documentation
```

## Coding Standards

### General Guidelines
- Follow PEP 8 style guide
- Maximum line length: 120 characters
- Use type hints with Pydantic models
- Write docstrings for public functions and classes
- Prefer composition over inheritance where appropriate
- Use logging instead of print statements

### Python Conventions
- Use `snake_case` for variables and functions
- Use `PascalCase` for class names
- Use `UPPER_CASE` for constants
- Private methods/attributes prefixed with underscore
- Module-level docstrings for packages

### Error Handling
- Use specific exception types
- Log errors with appropriate levels (debug, info, warning, error, critical)
- Fail early with clear error messages
- Validate inputs at boundaries

### Testing
- Write unit tests for new functionality
- Use existing test patterns in `tests/` directory
- Test both happy paths and edge cases
- Maintain test coverage for critical paths

## Domain-Specific Patterns

### Node Types
The system uses various node types defined in `TriccNodeType` enum:
- **Flow anchors**: `start`, `activity_start`, `activity_end`, `end`
- **Questions**: `select_one`, `select_multiple`, `select_yesno`, `note`
- **Inputs**: `integer`, `decimal`, `text`, `date`
- **Logic**: `calculate`, `rhombus`, `wait`, `add`, `count`
- **Navigation**: `goto`, `link_in`, `link_out`, `bridge`
- **Diagnosis**: `diagnosis`, `proposed_diagnosis`

### Expression System
- Expressions are built using `TriccOperation` with `TriccOperator` enum
- Operators include boolean logic, arithmetic, comparisons, and domain-specific functions
- Use `TriccReference` for variable references
- Expressions are evaluated lazily during graph processing

### Strategy Pattern
- Input strategies: `DrawioStrategy` (default)
- Output strategies: `XLSFormStrategy`, `XLSFormCHTStrategy`, `XLSFormCHTHFStrategy`, etc.
- Each strategy handles specific conversion requirements

### Graph Processing
- Nodes are connected via edges with optional labels
- Processing follows topological order when possible
- Support for multiple activity instances and cross-page linking
- Experimental pages have limited processing

## Documentation Requirements

### When Adding Features
1. Update relevant documentation in `docs/` directory
2. Add inline code comments for complex logic
3. Update README if user-facing changes
4. Add type hints to all function signatures
5. Include docstrings with Args, Returns, Raises sections

### Documentation Structure
- `docs/getting-started.md` - Installation and basic usage
- `docs/cli-and-inputs.md` - Command-line interface documentation
- `docs/tricc-elements.md` - Element reference and semantics
- `docs/pipeline.md` - Processing pipeline explanation
- `docs/visual-authoring-concepts.md` - Visual design patterns
- `docs/troubleshooting.md` - Common issues and solutions
- `docs/desing/FHIRcore.md` - Detailed spec for the FHIR / OpenSRP output strategy (including CQL architecture)
- `docs/open-srp-export.md` - User-facing guide for OpenSRP/FHIR-Core export
- `docs/planning/` - Implementation plans (e.g. FHIR remediation plan)

## Common Workflows

### Adding a New Output Strategy
1. Create class inheriting from `BaseOutputStrategy`
2. Implement required methods: `convert()`, `validate()`
3. Register strategy using `@register_input_strategy("Name")` or `@register_output_strategy("Name")` (see `tricc_oo/strategies/registry.py`)
4. Add tests for conversion logic
5. Document strategy capabilities and limitations

**FHIR-specific notes** (when working on `FHIRStrategy` / `OpenSRPStrategy`):
- Follow the refined CQL architecture: one Helper library + thin per-segment libraries.
- Use simple names in Questionnaire expressions.
- Prefer concept-driven data access in the Helper library over raw paths.
- Update the FHIR remediation plan and main docs when making architectural changes.

### Adding a New Node Type
1. Add to `TriccNodeType` enum in `models/base.py`
2. Define Pydantic model inheriting from `TriccNodeBaseModel`
3. Update `drawio_type_map.py` for XML mapping
4. Implement conversion logic in appropriate converter
5. Add to documentation in `docs/tricc-elements.md`

### Modifying Expression Logic
1. Update `TriccOperator` enum if new operators needed
2. Modify expression building in `converters/` directory
3. Update operator mappings and evaluation logic
4. Add comprehensive tests for expression evaluation
5. Document operator behavior and return types

### FHIR CQL / Library Generation (FHIRStrategy)
- Use a **Helper** library for all FHIR resource access (Observations, Conditions, etc.) keyed by concept name/code.
- Keep per-process/segment libraries **thin** — they should mostly contain named `define` statements that delegate to the Helper.
- In Questionnaire `calculatedExpression` / `initialExpression`, use **simple define names only** (e.g. `"Calc_bmi"`). Do not qualify with library name.
- The Questionnaire declares its library/libraries at the top level (via `library` element or SDC `cqlInputResources` extension).
- Avoid embedding raw questionnaire answer paths (`%resource.item.where(...)`) in CQL. Route data access through the Helper using concept identifiers.
- Follow patterns from pyfhirsdc and WHO SMART CQL examples (thin form libs + rich base/helper libs).
- When adding new CQL helpers or changing the template, update `docs/desing/FHIRcore.md` and `docs/open-srp-export.md`.

## Validation Checklist

Before committing code changes:

- [ ] Code follows PEP 8 and project style (120 char lines)
- [ ] All public functions have type hints
- [ ] Docstrings added for public APIs
- [ ] No print statements (use logging)
- [ ] Error handling is appropriate
- [ ] Tests pass (`python -m pytest tests/`)
- [ ] Documentation updated if needed
- [ ] No breaking changes to existing APIs
- [ ] Import statements are clean and organized
- [ ] No hardcoded values (use constants/config)
- [ ] Security considerations addressed (file paths, injections)

## Testing Guidelines

### Running Tests
```bash
# Run all tests
python -m pytest tests/

# Run specific test file
python tests/test_cql.py

# Build and test conversion
python tests/build.py -i tests/data/demo.drawio -o tests/output/
```

### Test Data
- Use files in `tests/data/` directory
- Draw.io files: `demo.drawio`, `combacal.drawio`, `etat.drawio`
- YAML fixtures (preferred for transformation testing): `tests/data/yaml/`
- JSON files for specific formats: `medlacreator.json`

See `docs/testing/transformation-test-coverage.md` for a detailed mapping of core transformation methods (`load_calculate`, inheritance/versioning, expression generation, etc.) to recommended test cases.

### Expected Outputs
- Check `tests/output/` directory for generated files
- Compare against expected outputs
- Validate XLSForm, CHT, or other format-specific outputs

## Debugging Tips

### Common Issues
1. **XML Parse Errors**: Check draw.io file format (must be valid XML)
2. **Expression Errors**: Verify operator syntax and reference validity
3. **Graph Errors**: Check for cycles or disconnected nodes
4. **Strategy Errors**: Ensure correct strategy for output format

### Logging
- Use `logger.debug()` for detailed processing info
- Use `logger.warning()` for recoverable issues
- Use `logger.error()` for failures
- Check `log.txt` for execution logs

### Validation
- Use `tricc_type` to identify node types
- Check `instance` numbers for multi-instance activities
- Verify edge connections and labels
- Validate expression references exist in graph

## Performance Considerations

- Process large diagrams incrementally when possible
- Cache computed expressions to avoid recalculation
- Use efficient data structures (OrderedSet for ordered collections)
- Profile before optimizing critical paths
- Consider memory usage for large graphs

## Security Notes

- Validate file paths to prevent directory traversal
- Sanitize user inputs in expressions
- Be cautious with XML parsing (XXE prevention)
- Validate external URLs before downloading
- Use appropriate file permissions for outputs

## Resources

- **Main Repository**: https://github.com/SwissTPH/tricc
- **Documentation**: https://swisstph.github.io/tricc/
- **Issue Tracker**: https://github.com/SwissTPH/tricc/issues
- **PyPI Package**: tricc-oo

## Quick Reference

### Important Files
- `tricc_oo/models/base.py` - Core data models
- `tricc_oo/converters/xml_to_tricc.py` - Draw.io to TRICC conversion
- `tricc_oo/strategies/` - Input/output strategy implementations
- `tests/build.py` - Main entry point for conversions
- `pyproject.toml` - Project configuration and dependencies

### Key Commands
```bash
# Convert a drawio file
tricc -i input.drawio -o output/

# Specify output strategy
tricc -i input.drawio -o output/ -O XLSFormCHTStrategy

# Set form ID
tricc -i input.drawio -o output/ -d my_form_id

# Set log level
tricc -i input.drawio -o output/ -l d  # debug
```

### Common Patterns
- Use `generate_id()` for creating unique identifiers
- Use `get_rand_name()` for human-readable names
- Use `OrderedSet` for maintaining order without duplicates
- Use Pydantic validation for data integrity
- Follow strategy pattern for extensibility

## file changes request format

SEARCH AND REPLACE ARE MANDATORY
``` 
------- SEARCH
            var ftpClient = GetOrCreateFtpClient(machineName);
=======
            var ftpClient = GetOrCreateFtpClient(machineName);
            X
+++++++ REPLACE
```