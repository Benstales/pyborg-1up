import attr
from typing import Callable, Dict, Any, List, Optional

from pyborg.pyborg_custom import PyborgBot


@attr.s
class PyborgCommand:
    """Pyborg command class"""
    name: str = attr.ib()
    command_callable: Callable[..., Any] = attr.ib()
    help: str = attr.ib()(default="")
    owner_permission: bool = attr.ib()(default=False)

    def __call__(self, pyborg: PyborgBot, command_list: List[str] = None, owner: bool = False) -> Any:
        """Execute the command"""
        # owner_permission => owner
        if not self.owner_permission or owner:
            return self.command_callable(pyborg, command_list=command_list)
        else:
            pyborg.logger.warning(f"Execution of the command '{self.name}' is not possible because you are not the owner")
            return None

    def display_help(self):
        """Display the command help instruction."""
        # owner_permission => own
        help_msg = self.help
        if self.owner_permission:
            help_msg += " (OWNER PERMISSION REQUIRED)"
        return help_msg


@attr.s
class PyborgCommandDict:
    """Pyborg command dict class"""
    command_dict: Dict[str, PyborgCommand] = attr.ib(default={})

    @classmethod
    def from_list_command(cls, list_new_commands: List[PyborgCommand]) -> "PyborgCommandDict":
        instance = PyborgCommandDict()
        instance.add_commands(list_new_commands)
        return instance

    def add_command(self, new_command: PyborgCommand):
        self.command_dict[new_command.name] = new_command

    def add_commands(self, list_new_commands: List[PyborgCommand]):
        for new_command in list_new_commands:
            self.add_command(new_command)

    def get_command(self, command_name: str) -> PyborgCommand:
        return self.command_dict[command_name]

    def __call__(self, pyborg: PyborgBot, command_name: str, command_list: List = None, owner: bool = False) -> Any:
        """Execute the command specified"""
        return self.command_dict[command_name](pyborg, command_list=command_list, owner=owner)

    def __repr__(self) -> str:
        """Return the dictionary string representation"""
        return str(self.command_dict)

    def __str__(self) -> str:
        """Return the list of command available"""
        return " | ".join([cmd for cmd in self.command_dict.keys()])

    def __contains__(self, item):
        return item in self.command_dict
