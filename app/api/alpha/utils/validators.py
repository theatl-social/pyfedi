def string_expected(values: list, data: dict):
    for v in values:
        if v in data:
            if not isinstance(data[v], str) and not isinstance(data[v], type(None)):
                raise Exception("string_expected_for_" + v)


def integer_expected(values: list, data: dict):
    for v in values:
        if v in data:
            if (
                not isinstance(data[v], int) and not isinstance(data[v], type(None))
            ) or isinstance(data[v], bool):
                raise Exception("integer_expected_for_" + v)


def boolean_expected(values: list, data: dict):
    for v in values:
        if v in data:
            if not isinstance(data[v], bool) and not isinstance(data[v], type(None)):
                raise Exception("boolean_expected_for_" + v)


def array_of_strings_expected(values: list, data: dict):
    for v in values:
        if v in data:
            if not isinstance(data[v], list) and not isinstance(data[v], type(None)):
                raise Exception("array_expected_for_" + v)
            for i in data[v]:
                if not isinstance(i, str):
                    raise Exception("array_of_strings_expected_for_" + v)


def array_of_integers_expected(values: list, data: dict):
    for v in values:
        if v in data:
            if not isinstance(data[v], list) and not isinstance(data[v], type(None)):
                raise Exception("array_expected_for_" + v)
            for i in data[v]:
                if not isinstance(i, int):
                    raise Exception("array_of_integers_expected_for_" + v)


def required(values: list, data: dict):
    for v in values:
        if v not in data:
            raise Exception("missing_required_" + v + "_field")
