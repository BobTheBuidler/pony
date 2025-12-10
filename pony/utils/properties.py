from typing import Callable, Final, Generic, Optional, Type, TypeVar, Union, final, overload


_O = TypeVar("_O")
_C = TypeVar("_C", bound=type)
_T = TypeVar("_T")


@final
class cached_property(Generic[_O, _T]):
    """
    A property that is only computed once per instance and then replaces itself
    with an ordinary attribute. Deleting the attribute resets the property.
    Source: https://github.com/bottlepy/bottle/commit/fa7733e075da0d790d809aa3d2f53071897e6f76
    """  # noqa

    def __init__(self, func: Callable[[_O], _T]):
        self.__doc__: Final = getattr(func, '__doc__')
        self.func: Final = func

    @overload
    def __get__(self, obj: None, cls: Type[_O]) -> "cached_property[_O, _T]": ...
    @overload
    def __get__(self, obj: _O, cls: Type[_O]) -> _T: ...
    def __get__(self, obj: Optional[_O], cls: Type[_O]) -> Union[_T, "cached_property[_O, _T]"]:
        if obj is None:
            return self
        value = obj.__dict__[self.func.__name__] = self.func(obj)
        return value


@final
class class_property(Generic[_C, _T]):
    """
    Read-only class property
    """

    def __init__(self, func: Callable[[_C], _T]):
        self.func: Final = func

    def __get__(self, obj: _C, cls: Type[_C]) -> _T:
        return self.func(cls)


@final
class class_cached_property(Generic[_C, _T]):

    def __init__(self, func: Callable[[_C], _T]):
        self.func: Final = func
        self._func_name: Final = func.__name__

    def __get__(self, obj: _C, cls: Type[_C]) -> _T:
        value = self.func(cls)
        setattr(cls, self._func_name, value)
        return value
