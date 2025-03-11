import os
import json
from pathlib import Path
from tricc_oo.converters.codesystem_to_ocl import transform_fhir_to_ocl

def find_and_process_codesystems(directory_path):
    # Convert string path to Path object if not already
    dir_path = Path(directory_path)
    
    # Find all JSON files in the directory
    for json_file in dir_path.glob("*.json"):
        try:
            # Read the JSON file
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
                # Check if resource_type is CodeSystem
                if data.get("resourceType") == "CodeSystem":
                    # Get the filename without extension for output naming
                    file_key = json_file.stem
                    
                    # Write the original CodeSystem JSON
                    output_cs_path = dir_path / f"{file_key}_codesystem.json"
                    with open(output_cs_path, "w", encoding='utf-8') as file:
                        file.write(json.dumps(data, indent=4))
                    
                    # Transform to OCL payload
                    ocl_payload = transform_fhir_to_ocl(
                        data,
                        source_name="ALM",
                        source_owner="pdelcroix",
                        source_owner_type="User"
                    )
                    
                    # Save the transformed OCL payload
                    output_ocl_path = dir_path / f"{file_key}_ocl_bulk_upload.json"
                    with open(output_ocl_path, "w", encoding='utf-8') as f:
                        for item in ocl_payload:
                            json_line = json.dumps(item.dict(exclude_none=True))
                            f.write(json_line + '\n')
                    
                    print(f"OCL bulk upload payload generated successfully for {file_key}!")
                    
        except json.JSONDecodeError:
            print(f"Error: Invalid JSON in file {json_file}")
        except Exception as e:
            print(f"Error processing {json_file}: {str(e)}")

# Example usage
media_path = "path/to/your/directory"  # Replace with your directory path
find_and_process_codesystems(media_path)