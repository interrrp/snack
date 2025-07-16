import random
from pathlib import Path
from sys import argv, stderr
from typing import NoReturn, cast, final

import pygame

# fmt: off
FONTSET = [
    0xF0, 0x90, 0x90, 0x90, 0xF0, # 0
    0x20, 0x60, 0x20, 0x20, 0x70, # 1
    0xF0, 0x10, 0xF0, 0x80, 0xF0, # 2
    0xF0, 0x10, 0xF0, 0x10, 0xF0, # 3
    0x90, 0x90, 0xF0, 0x10, 0x10, # 4
    0xF0, 0x80, 0xF0, 0x10, 0xF0, # 5
    0xF0, 0x80, 0xF0, 0x90, 0xF0, # 6
    0xF0, 0x10, 0x20, 0x40, 0x40, # 7
    0xF0, 0x90, 0xF0, 0x90, 0xF0, # 8
    0xF0, 0x90, 0xF0, 0x10, 0xF0, # 9
    0xF0, 0x90, 0xF0, 0x90, 0x90, # A
    0xE0, 0x90, 0xE0, 0x90, 0xE0, # B
    0xF0, 0x80, 0x80, 0x80, 0xF0, # C
    0xE0, 0x90, 0x90, 0x90, 0xE0, # D
    0xF0, 0x80, 0xF0, 0x80, 0xF0, # E
    0xF0, 0x80, 0xF0, 0x80, 0x80, # F
]
# fmt: on

MEM_SIZE = 0xFFF
MEM_PROGRAM_START = 0x200


def fail(msg: str) -> NoReturn:
    print(msg, file=stderr)  # noqa: T201
    raise SystemExit(1)


@final
class Emulator:
    def __init__(self, title: str, program: bytes, ipf: int) -> None:
        self._mem = bytearray(MEM_SIZE)
        self._mem[0 : len(FONTSET)] = FONTSET
        self._mem[MEM_PROGRAM_START : len(program)] = program

        self._ipf = ipf
        self._pc: int = MEM_PROGRAM_START

        self._registers = [0] * 16
        self._i = 0

        self._keys = [0] * 16

        self._call_stack: list[int] = []

        self._delay_timer = 0
        self._sound_timer = 0

        pygame.init()
        self._surface = pygame.Surface((64, 32))
        self._real_screen_size = (self._surface.width * 16, self._surface.height * 16)
        self._screen = pygame.display.set_mode(self._real_screen_size, vsync=1)
        pygame.display.set_caption(title)

    def run(self) -> None:
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    self._on_key(cast("int", event.key), down=True)
                elif event.type == pygame.KEYUP:
                    self._on_key(cast("int", event.key), down=False)

            for _ in range(self._ipf):
                self._cycle()

            self._screen.blit(pygame.transform.scale(self._surface, self._real_screen_size))
            pygame.display.flip()

    def _cycle(self) -> None:
        if self._update_timers():
            return
        self._do_instruction()

    def _update_timers(self) -> bool:
        if self._delay_timer == 0 and self._sound_timer == 0:
            return False

        if self._delay_timer > 0:
            self._delay_timer -= 1

        if self._sound_timer > 0:
            self._sound_timer -= 1

        return True

    def _do_instruction(self) -> None:  # noqa: C901, PLR0912, PLR0915
        opcode, op, x, y, n, nn, nnn = self._fetch()
        self._pc += 2

        match op:
            case 0 if opcode == 0x00E0:
                self._surface.fill("black")

            case 0 if opcode == 0x00EE:
                try:
                    self._pc = self._call_stack.pop()
                except IndexError as e:
                    msg = "RET outside subroutine"
                    raise RuntimeError(msg) from e

            case 0x1:
                self._pc = nnn

            case 0x2:
                self._call_stack.append(self._pc)
                self._pc = nnn

            case 0x3:
                if self._registers[x] == nn:
                    self._pc += 2

            case 0x4:
                if self._registers[x] != nn:
                    self._pc += 2

            case 0x5:
                if self._registers[x] == self._registers[y]:
                    self._pc += 2

            case 0x6:
                self._registers[x] = nn

            case 0x7:
                self._registers[x] = (self._registers[x] + nn) & 0xFF

            case 0x8:
                match n:
                    case 0x0:
                        self._registers[x] = self._registers[y]
                    case 0x1:
                        self._registers[x] |= self._registers[y]
                    case 0x2:
                        self._registers[x] &= self._registers[y]
                    case 0x3:
                        self._registers[x] ^= self._registers[y]
                    case 0x4:
                        total = self._registers[x] + self._registers[y]
                        self._registers[0xF] = 1 if total > 0xFF else 0
                        self._registers[x] = total & 0xFF
                    case 0x5:
                        self._registers[0xF] = 1 if self._registers[x] > self._registers[y] else 0
                        self._registers[x] = (self._registers[x] - self._registers[y]) & 0xFF
                    case 0x6:
                        self._registers[0xF] = self._registers[x] & 1
                        self._registers[x] >>= 1
                    case 0x7:
                        self._registers[0xF] = 1 if self._registers[y] > self._registers[x] else 0
                        self._registers[x] = (self._registers[y] - self._registers[x]) & 0xFF
                    case 0xE:
                        self._registers[0xF] = (self._registers[x] >> 7) & 1
                        self._registers[x] = (self._registers[x] << 1) & 0xFF
                    case _:
                        pass

            case 0x9 if n == 0x0:
                if self._registers[x] != self._registers[y]:
                    self._pc += 2

            case 0xA:
                self._i = nnn

            case 0xB:
                self._pc = nnn + self._registers[0]

            case 0xC:
                self._registers[x] = random.randint(0, 255) & nn  # noqa: S311

            case 0xD:
                vx, vy = self._registers[x], self._registers[y]
                self._registers[0xF] = 0
                for row in range(n):
                    sprite = self._mem[self._i + row]
                    for bit in range(8):
                        if (sprite >> (7 - bit)) & 1:
                            px = (vx + bit) % 64
                            py = (vy + row) % 32
                            color = self._surface.get_at((px, py)) != pygame.Color("black")
                            if color:
                                self._registers[0xF] = 1
                            self._surface.set_at(
                                (px, py),
                                pygame.Color("black") if color else pygame.Color("white"),
                            )

            case 0xE if nn == 0x9E:
                if self._keys[self._registers[x]]:
                    self._pc += 2

            case 0xE if nn == 0xA1:
                if not self._keys[self._registers[x]]:
                    self._pc += 2

            case 0xF if nn == 0x0A:
                for key, pressed in enumerate(self._keys):
                    if pressed:
                        self._registers[x] = key
                        break
                else:
                    # No key pressed, rewind PC to re-run this instruction
                    self._pc -= 2

            case 0xF:
                match nn:
                    case 0x07:
                        self._registers[x] = self._delay_timer
                    case 0x15:
                        self._delay_timer = self._registers[x]
                    case 0x18:
                        self._sound_timer = self._registers[x]
                    case 0x1E:
                        self._i = (self._i + self._registers[x]) & 0xFFFF
                    case 0x29:
                        self._i = self._registers[x] * 5
                    case 0x33:
                        value = self._registers[x]
                        self._mem[self._i] = value // 100
                        self._mem[self._i + 1] = (value // 10) % 10
                        self._mem[self._i + 2] = value % 10
                    case 0x55:
                        for i in range(x + 1):
                            self._mem[self._i + i] = self._registers[i]
                    case 0x65:
                        for i in range(x + 1):
                            self._registers[i] = self._mem[self._i + i]
                    case _:
                        pass

            case _:
                fail(f"Unable to handle {opcode:04X}")

    def _fetch(self) -> tuple[int, int, int, int, int, int, int]:
        opcode = int.from_bytes(self._mem[self._pc : self._pc + 2])
        return (
            opcode,
            (opcode & 0xF000) >> 12,
            (opcode & 0x0F00) >> 8,
            (opcode & 0x00F0) >> 4,
            (opcode & 0x000F),
            (opcode & 0x00FF),
            (opcode & 0x0FFF),
        )

    def _on_key(self, keycode: int, *, down: bool) -> None:
        # fmt: off
        key_map = {
            pygame.K_1: 0x1, pygame.K_2: 0x2, pygame.K_3: 0x3, pygame.K_4: 0xC,
            pygame.K_q: 0x4, pygame.K_w: 0x5, pygame.K_e: 0x6, pygame.K_r: 0xD,
            pygame.K_a: 0x7, pygame.K_s: 0x8, pygame.K_d: 0x9, pygame.K_f: 0xE,
            pygame.K_z: 0xA, pygame.K_x: 0x0, pygame.K_c: 0xB, pygame.K_v: 0xF,
        }
        # fmt: on
        if keycode in key_map:
            self._keys[key_map[keycode]] = int(down)


def run(program_path: str, ipf: int) -> None:
    try:
        program = Path(program_path).read_bytes()
    except FileNotFoundError:
        fail(f"{program_path} does not exist")

    Emulator(program_path, program, ipf).run()


def main() -> None:
    match argv[1:]:
        case [program_path, ipf]:
            try:
                ipf = int(ipf)
            except ValueError:
                fail(f"IPF must be an integer (got {ipf})")
            if ipf < 1:
                fail("IPF must be above 0")
            run(program_path, ipf)

        case [program_path]:
            run(program_path, ipf=11)

        case _:
            fail("Usage: snack <program path> [ipf=11]")


if __name__ == "__main__":
    main()
