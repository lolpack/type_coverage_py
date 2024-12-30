import ast
import os
from typing import List, Tuple, Dict

def get_fully_qualified_name(node: ast.FunctionDef, module: str, parent_map: Dict[ast.AST, ast.AST]) -> str:
    parent = parent_map.get(node)
    if isinstance(parent, ast.ClassDef):
        return f"{module}.{parent.name}.{node.name}"
    return f"{module}.{node.name}"

def build_parent_map(tree: ast.AST) -> Dict[ast.AST, ast.AST]:
    parent_map: Dict[ast.AST, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parent_map[child] = node
    return parent_map

def calculate_parameter_coverage(files: List[str]) -> Tuple[int, int, int]:
    total_params: int = 0
    annotated_params: int = 0
    skipped_files: int = 0

    # To track annotations and parameters per function
    function_param_counts: Dict[str, Tuple[int, int]] = {}
    functions_covered_by_pyi: set[str] = set()
    
    for file in files:
        try:
            module_name = os.path.splitext(os.path.basename(file))[0]
            with open(file, 'r', encoding='utf-8', errors='ignore') as f:
                tree = ast.parse(f.read(), filename=file)
                parent_map = build_parent_map(tree)

                # Use a set to track already analyzed functions
                analyzed_functions: set[str] = set()

                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef):
                        func_name = get_fully_qualified_name(node, module_name, parent_map)

                        # Skip if already analyzed
                        if func_name in analyzed_functions:
                            continue

                        analyzed_functions.add(func_name)

                        # Exclude 'self' and 'cls' from parameters
                        params = [arg for arg in node.args.args if arg.arg not in ('self', 'cls')]
                        param_count = len(params)
                        annotation_count = sum(1 for arg in params if arg.annotation is not None)

                        # Handle .pyi files and function overwriting
                        if file.endswith(".pyi"):
                            functions_covered_by_pyi.add(func_name)
                            function_param_counts[func_name] = (param_count, annotation_count)
                        elif func_name not in functions_covered_by_pyi:
                            if func_name not in function_param_counts:
                                function_param_counts[func_name] = (param_count, annotation_count)

        except (SyntaxError, UnicodeDecodeError):
            skipped_files += 1

    # Sum up the final counts
    total_params = sum(counts[0] for counts in function_param_counts.values())
    annotated_params = sum(counts[1] for counts in function_param_counts.values())

    return total_params, annotated_params, skipped_files

def calculate_return_type_coverage(files: List[str]) -> Tuple[int, int, int]:
    total_functions: int = 0
    annotated_functions: int = 0
    skipped_files: int = 0

    # To track return type annotations per function
    function_return_counts: Dict[str, Tuple[int, int]] = {}
    functions_covered_by_pyi: set[str] = set()

    for file in files:
        try:
            module_name = os.path.splitext(os.path.basename(file))[0]
            with open(file, 'r', encoding='utf-8', errors='ignore') as f:
                tree = ast.parse(f.read(), filename=file)
                parent_map = build_parent_map(tree)

                # Use a set to track already analyzed functions
                analyzed_functions: set[str] = set()

                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef):
                        func_name = get_fully_qualified_name(node, module_name, parent_map)

                        # Skip if already analyzed
                        if func_name in analyzed_functions:
                            continue

                        analyzed_functions.add(func_name)

                        # Skip the __init__ method
                        if node.name == "__init__":
                            continue

                        # Handle .pyi files and function overwriting
                        if file.endswith(".pyi"):
                            functions_covered_by_pyi.add(func_name)
                            function_return_counts[func_name] = (1, 1 if node.returns is not None else 0)
                        elif func_name not in functions_covered_by_pyi:
                            if func_name not in function_return_counts:
                                function_return_counts[func_name] = (
                                    1,
                                    1 if node.returns is not None else 0
                                )

        except (SyntaxError, UnicodeDecodeError):
            skipped_files += 1

    # Sum up the final counts
    total_functions = sum(counts[0] for counts in function_return_counts.values())
    annotated_functions = sum(counts[1] for counts in function_return_counts.values())

    return total_functions, annotated_functions, skipped_files

def calculate_overall_coverage(files: List[str]) -> Dict[str, float]:
    total_params, annotated_params, param_skipped = calculate_parameter_coverage(files)
    total_functions, annotated_functions, return_skipped = calculate_return_type_coverage(files)

    total_skipped: int = max(param_skipped, return_skipped)

    return {
        "parameter_coverage": calculuate_coverage(annotated_params, total_params),
        "return_type_coverage": calculuate_coverage(annotated_functions, total_functions),
        "skipped_files": total_skipped
    }

def calculuate_coverage(covered: int, total: int) -> float:
    return (covered / total) * 100 if total > 0 else -1.0
