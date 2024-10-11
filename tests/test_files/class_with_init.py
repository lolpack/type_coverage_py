# class_with_init.py

class MyClass:
    def __init__(self, name: str, age: int):
        # __init__ method with parameters that should be skipped in coverage calculation
        self.name = name
        self.age = age

    def greet(self) -> str:
        # Method with full type annotations
        return f"Hello, my name is {self.name} and I am {self.age} years old."