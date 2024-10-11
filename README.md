# type_coverage_py

Calculate the Type Coverage for top Python packages.

Take the top pypi packages pulled from this project [https://github.com/hugovk/top-pypi-packages](https://github.com/hugovk/top-pypi-packages)

View report here: [https://html-preview.github.io/?url=https://github.com/lolpack/type_coverage_py/blob/main/index.html](https://html-preview.github.io/?url=https://github.com/lolpack/type_coverage_py/blob/main/index.html)

## Methodology

This section outlines how the script analyzes Python packages, checks for typeshed availability, and calculates type coverage. The process involves three key steps: package extraction, typeshed check, and type coverage calculation.

### **Package Extraction**

- **Downloading**: The script downloads the source distribution of each selected package from PyPI and extracts it into a temporary directory.
- **File Extraction**: It identifies and extracts all Python files (`.py`) and type stub files (`.pyi`) from the package for analysis.

### **Typeshed Check**

- **Typeshed Directory**: The script checks if a corresponding stub exists in the `typeshed` repository, which contains type stubs for standard library modules and popular third-party packages.
- **Existence Check**: If a typeshed stub exists, it is recorded as `HasTypeShed: Yes`; otherwise, it is marked as `HasTypeShed: No`.
- **Typeshed Merge**: Pull available typestubs from typeshed with the same package name. If a local `.pyi` file exists, prefer it over typeshed. 

### **Type Coverage Calculation**

- **Parameter Coverage**: 
  - The script analyzes function definitions in the extracted files and calculates the percentage of function parameters that have type annotations.
  - **Handling `.pyi` files**: If a function is defined in a `.pyi` file, it takes precedence over any corresponding function in a `.py` file. The parameter counts from `.pyi` files will overwrite those from `.py` files for the same function.
  - The formula used:
  $$\[
  \text{Parameter Coverage} = \left( \frac{\text{Number of Parameters with Type Annotations}}{\text{Total Number of Parameters}} \right) \times 100
  \]$$

- **Return Type Coverage**:
  - The script calculates the percentage of functions that have return type annotations.
  - **Handling `.pyi` files**: Similar to parameter coverage, if a function is defined in a `.pyi` file, the return type annotations from the `.pyi` file will overwrite those from any corresponding `.py` file.
  - The formula used:
  $$\[
  \text{Return Type Coverage} = \left( \frac{\text{Number of Functions with Return Type Annotations}}{\text{Total Number of Functions}} \right) \times 100
  \]$$

- **Skipped Files**:
  - Files that cannot be processed due to syntax or encoding errors are skipped, and the number of skipped files is recorded.

- **Overall Coverage**:
  - The script calculates and returns the overall coverage, combining parameter coverage and return type coverage. The maximum number of skipped files between the parameter and return type calculations is recorded.

This methodology ensures an accurate and detailed analysis of type coverage for popular Python packages, taking into account the presence of type stub files (`.pyi`) which are prioritized over implementation files (`.py`) for the same functions.


## Usage

Clone the typeshed repo into the root of the project

`git clone git@github.com:python/typeshed.git`

Call the main function with the top N packages to analyze, the max is 8,000.

`python main.py 100`

Alternatively call with a single package

`python main.py --package-name flask`

Analyze the top N packages and generate both JSON and HTML reports:

`python main.py 100 --write-json --write-html`
