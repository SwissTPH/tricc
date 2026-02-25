# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.6.31] - 2026-02-13

### Added
- Add priority support for nodes in XML to TRICC conversion
- Add DiagnosisList operation support for CQL to XLS form conversion
- Add original references support to XLS operations and fix variable initialization
- Add sequence and data fields to models, serializers, and visitors
- Add SymPy-based simplification for models
- Add Google Drive download support with authentication
- Enhance XLS form sequence handling for CHT
- Enhance version inheritance to merge all previous versions and expressions
- Enhance operation simplification to preserve istrue semantics
- Enhance relevance processing and XLS form export features
- Update survey diagram with improved naming and logic in demo

### Fixed
- Optimize node reordering and reduce logging in dependency loops
- Include activity relevance for non-input prev nodes in expression building
- Exclude current node from past instances in get_prev_instance_skip_expression
- Fix TriccOperation argument to accept list in visitor
- Fix clean_and_list bug in models

### Changed
- Rename datatype to dataType and context_type to concept_type for API consistency
- Move group calculate creation and update JAR sourcing
- Adjust priority constants and refine node priority logic
- Update more info handling and disable help nodes
- Clean up XML converter and fix expression handling

### Dependencies
- Bump urllib3 from 2.2.2 to 2.6.3