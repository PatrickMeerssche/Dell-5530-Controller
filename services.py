import awelc


class LedService:
    # Thin wrapper around low-level awelc calls to keep UI code decoupled.

    def set_static(self, red, green, blue):
        awelc.set_static(red, green, blue)

    def set_morph(self, red, green, blue, duration):
        awelc.set_morph(red, green, blue, duration)

    def remove_animation(self):
        awelc.remove_animation()

    def set_dim(self, level):
        awelc.set_dim(level)


class AcpiService:
    # Encapsulates privileged shell communication and ACPI argument templating.

    def __init__(self, shell, acpi_cmd, acpi_call_dict):
        self.shell = shell
        self.acpi_cmd = acpi_cmd
        self.acpi_call_dict = acpi_call_dict

    def shell_exec(self, cmd: str):
        print("Bash: Executing {}".format(cmd))
        self.shell.sendline(cmd)
        self.shell.expect("[#$] ")
        result = self.shell.before
        result = result.split('\n')
        for line in result[1:]:
            print(line)
        return result

    def parse_shell_exec(self, line: str):
        return line[line.find('\r') + 1:line.find('\x00')]

    def call(self, cmd, arg1="0x00", arg2="0x00"):
        args = self.acpi_call_dict[cmd]
        if len(args) == 4:
            cmd_current = self.acpi_cmd.format(args[0], args[1], args[2], args[3])
        elif len(args) == 3:
            cmd_current = self.acpi_cmd.format(args[0], args[1], args[2], arg1)
        elif len(args) == 2:
            cmd_current = self.acpi_cmd.format(args[0], args[1], arg1, arg2)
        else:
            cmd_current = ""
        return self.parse_shell_exec(self.shell_exec(cmd_current)[2])
