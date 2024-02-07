from fastapi import Form


def form_body(prefix: str = ""):
    def inner(cls):
        parameters = []
        for arg in cls.__signature__.parameters.values():
            parameters.append(arg.replace(default=Form(arg.default, alias=f"{prefix}{arg.name}")))
        cls.__signature__ = cls.__signature__.replace(parameters=parameters)
        return cls

    return inner
