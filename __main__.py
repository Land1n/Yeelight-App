from __future__ import annotations

import json
import os
import re
from pathlib import Path

import flet as ft
import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


HELP_TEXT = """Доступные команды

Лампы
  discover                         найти Yeelight в локальной сети
  list                             показать добавленные лампы
  add <IP>                         добавить лампу по IPv4-адресу
  status <IP>                      получить состояние лампы
  on <IP> / off <IP>               включить или выключить лампу
  toggle <IP>                      переключить состояние
  brightness <IP> <1-100>          установить яркость
  color <IP> <#RRGGBB>             установить цвет
  temp <IP> <1700-6500>            установить цветовую температуру

Консоль
  help                             показать эту справку
  clear                            очистить вывод консоли"""


def local_command(text: str) -> str | None:
    """Return a local console action, or None for a server command."""
    command = text.strip().casefold()
    if command in {"help", "?"}:
        return "help"
    if command in {"clear", "cls"}:
        return "clear"
    return None


def main(page: ft.Page) -> None:
    page.title = "Yeelight"
    page.padding = 20
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = "#0b1018"
    page.scroll = ft.ScrollMode.AUTO

    server_url = ft.TextField(
        label="Адрес сервера",
        value=os.getenv("YEELIGHT_SERVER_URL", "http://127.0.0.1:8000"),
        keyboard_type=ft.KeyboardType.URL,
        autocorrect=False,
        expand=True,
        border_color="#344153",
        focused_border_color="#b6e36b",
        text_size=14,
    )
    api_token = ft.TextField(
        label="API-токен",
        hint_text="Не нужен, если сервер запущен без токена",
        password=True,
        can_reveal_password=True,
        value=os.getenv("YEELIGHT_API_TOKEN", ""),
        expand=True,
        border_color="#344153",
        focused_border_color="#b6e36b",
        text_size=14,
    )
    status = ft.Text("Подключаемся…", size=12, color="#f6c85f")
    output = ft.ListView(expand=True, spacing=8, auto_scroll=True)
    bulbs = ft.Column(spacing=10)
    command = ft.TextField(
        label="Команда",
        hint_text="Например: discover, help или on 192.168.1.45",
        autocorrect=False,
        expand=True,
        border_color="#344153",
        focused_border_color="#b6e36b",
        text_size=14,
    )
    send_button = ft.Button(
        content=ft.Text("Выполнить"),
        icon=ft.Icons.PLAY_ARROW,
        style=ft.ButtonStyle(
            bgcolor="#b6e36b",
            color="#15200e",
            shape=ft.RoundedRectangleBorder(radius=12),
        ),
    )
    busy = False

    def card(content: ft.Control, *, padding: int = 18) -> ft.Container:
        return ft.Container(
            content=content,
            padding=padding,
            bgcolor="#151e2a",
            border=ft.Border.all(1, "#293747"),
            border_radius=18,
        )

    def section_title(title: str, subtitle: str | None = None) -> ft.Column:
        items = [ft.Text(title, size=17, weight=ft.FontWeight.BOLD, color="#f3f6fb")]
        if subtitle:
            items.append(ft.Text(subtitle, size=12, color="#91a0b3"))
        return ft.Column(items, spacing=4, tight=True)

    def log(message: str, color: str = "#d6deea") -> None:
        output.controls.append(
            ft.Text(
                message,
                selectable=True,
                color=color,
                font_family="monospace",
                size=12,
            )
        )
        if len(output.controls) > 100:
            del output.controls[:-100]

    async def request(path: str, *, command_text: str | None = None) -> dict:
        base_url = (server_url.value or "").strip().rstrip("/")
        if not re.fullmatch(r"https?://[^/]+", base_url, re.IGNORECASE):
            raise ValueError("Введите адрес сервера, например http://192.168.1.10:8000")

        headers = {"X-API-Token": (api_token.value or "").strip()}
        try:
            async with httpx.AsyncClient(timeout=35) as client:
                response = await client.request(
                    "POST" if command_text is not None else "GET",
                    f"{base_url}{path}",
                    headers=headers,
                    json={"command": command_text} if command_text is not None else None,
                )
        except httpx.RequestError as exc:
            raise RuntimeError(f"Не удалось подключиться к серверу: {exc}") from exc

        try:
            body = response.json()
        except ValueError as exc:
            raise RuntimeError(
                f"Сервер вернул некорректный ответ (HTTP {response.status_code})"
            ) from exc
        if not response.is_success:
            raise RuntimeError(body.get("detail", f"Ошибка HTTP {response.status_code}"))
        return body

    async def refresh_bulbs() -> None:
        result = await request("/api/bulbs")
        bulbs.controls.clear()
        if not result["bulbs"]:
            bulbs.controls.append(
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Icon(ft.Icons.LIGHTBULB_OUTLINE, size=30, color="#91a0b3"),
                            ft.Text(
                                "Пока нет ламп",
                                size=15,
                                weight=ft.FontWeight.BOLD,
                                text_align=ft.TextAlign.CENTER,
                            ),
                            ft.Text(
                                "Найдите лампы в сети или добавьте адрес командой add <IP>.",
                                size=12,
                                color="#91a0b3",
                                text_align=ft.TextAlign.CENTER,
                            ),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=7,
                    ),
                    padding=18,
                    bgcolor="#101722",
                    border_radius=14,
                )
            )
            return

        for bulb in result["bulbs"]:
            address = bulb["ip"]

            def make_handler(text: str):
                async def handler(_event) -> None:
                    await run_command(text)
                return handler

            bulbs.controls.append(
                ft.Container(
                    content=ft.ResponsiveRow(
                        [
                            ft.Container(
                                content=ft.Row(
                                    [
                                        ft.Container(
                                            content=ft.Icon(
                                                ft.Icons.LIGHTBULB,
                                                color="#b6e36b",
                                                size=22,
                                            ),
                                            padding=10,
                                            bgcolor="#263421",
                                            border_radius=12,
                                        ),
                                        ft.Column(
                                            [
                                                ft.Text(
                                                    address,
                                                    size=14,
                                                    weight=ft.FontWeight.BOLD,
                                                ),
                                                ft.Text("Yeelight • LAN", size=11, color="#91a0b3"),
                                            ],
                                            spacing=3,
                                            tight=True,
                                        ),
                                    ],
                                    spacing=12,
                                ),
                                col={"xs": 12, "sm": 5, "md": 6},
                            ),
                            ft.Container(
                                content=ft.Row(
                                    [
                                        ft.Button(
                                            content=ft.Text("Вкл"),
                                            icon=ft.Icons.POWER_SETTINGS_NEW,
                                            on_click=make_handler(f"on {address}"),
                                        ),
                                        ft.Button(
                                            content=ft.Text("Выкл"),
                                            on_click=make_handler(f"off {address}"),
                                        ),
                                        ft.Button(
                                            content=ft.Text("Статус"),
                                            on_click=make_handler(f"status {address}"),
                                        ),
                                    ],
                                    wrap=True,
                                    spacing=7,
                                ),
                                col={"xs": 12, "sm": 7, "md": 6},
                            ),
                        ],
                        run_spacing=10,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=14,
                    bgcolor="#101722",
                    border=ft.Border.all(1, "#253244"),
                    border_radius=14,
                )
            )

    async def run_command(text: str) -> None:
        nonlocal busy
        text = text.strip()
        if not text:
            return

        local_action = local_command(text)
        if local_action == "clear":
            output.controls.clear()
            page.update()
            return
        if local_action == "help":
            log(f"> {text}", "#b6e36b")
            log(HELP_TEXT, "#d6deea")
            page.update()
            return
        if busy:
            return

        busy = True
        send_button.disabled = True
        log(f"> {text}", "#b6e36b")
        page.update()
        try:
            result = await request("/api/commands", command_text=text)
            log(json.dumps(result["result"], ensure_ascii=False, indent=2))
            status.value = "Сервер подключён"
            status.color = "#b6e36b"
            if re.match(r"^(discover|add|list)\b", text):
                try:
                    await refresh_bulbs()
                except (RuntimeError, ValueError, KeyError) as exc:
                    log(f"Список ламп не обновлён: {exc}", "#ff8585")
        except (RuntimeError, ValueError, KeyError) as exc:
            log(f"Ошибка: {exc}", "#ff8585")
            status.value = "Нет подключения"
            status.color = "#ff8585"
        finally:
            busy = False
            send_button.disabled = False
            page.update()

    async def submit_command(_event) -> None:
        text = command.value or ""
        command.value = ""
        await run_command(text)

    async def refresh_clicked(_event) -> None:
        await run_command("list")

    def command_handler(text: str):
        async def handler(_event) -> None:
            await run_command(text)

        return handler

    command.on_submit = submit_command
    send_button.on_click = submit_command
    refresh_button = ft.Button(
        content=ft.Text("Обновить"),
        icon=ft.Icons.REFRESH,
        on_click=refresh_clicked,
    )
    discover_button = ft.Button(
        content=ft.Text("Найти лампы"),
        icon=ft.Icons.SEARCH,
        on_click=command_handler("discover"),
    )
    clear_button = ft.Button(
        content=ft.Text("Очистить"),
        icon=ft.Icons.DELETE_OUTLINE,
        on_click=command_handler("clear"),
    )
    help_button = ft.Button(
        content=ft.Text("Справка"),
        icon=ft.Icons.HELP_OUTLINE,
        on_click=command_handler("help"),
    )

    header = card(
        ft.Row(
            [
                ft.Row(
                    [
                        ft.Container(
                            content=ft.Icon(ft.Icons.LIGHTBULB, color="#17210f", size=25),
                            padding=11,
                            bgcolor="#b6e36b",
                            border_radius=14,
                        ),
                        ft.Column(
                            [
                                ft.Text("Yeelight", size=23, weight=ft.FontWeight.BOLD),
                                ft.Text("Управление освещением", size=12, color="#91a0b3"),
                            ],
                            spacing=2,
                            tight=True,
                        ),
                    ],
                    spacing=13,
                ),
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Container(width=8, height=8, bgcolor="#b6e36b", border_radius=4),
                            status,
                        ],
                        spacing=8,
                    ),
                    padding=ft.Padding.symmetric(horizontal=12, vertical=8),
                    bgcolor="#202b25",
                    border_radius=20,
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            wrap=True,
            spacing=12,
        )
    )

    connection_card = card(
        ft.Column(
            [
                section_title("Подключение", "Настройте адрес API и авторизацию"),
                ft.ResponsiveRow(
                    [
                        ft.Container(content=server_url, col={"xs": 12, "md": 6}),
                        ft.Container(content=api_token, col={"xs": 12, "md": 6}),
                    ],
                    spacing=12,
                    run_spacing=6,
                ),
            ],
            spacing=14,
        )
    )
    bulbs_card = card(
        ft.Column(
            [
                ft.Row(
                    [
                        section_title("Мои лампы", "Управляйте устройствами в вашей сети"),
                        ft.Row([discover_button, refresh_button], wrap=True, spacing=8),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    wrap=True,
                    spacing=12,
                ),
                bulbs,
            ],
            spacing=16,
        )
    )
    console_card = card(
        ft.Column(
            [
                ft.Row(
                    [
                        section_title("Командная строка", "Введите команду или воспользуйтесь справкой"),
                        ft.Row([help_button, clear_button], wrap=True, spacing=8),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    wrap=True,
                    spacing=12,
                ),
                ft.Container(
                    content=output,
                    height=260,
                    padding=14,
                    bgcolor="#0b111a",
                    border=ft.Border.all(1, "#263548"),
                    border_radius=14,
                ),
                ft.Row([command, send_button], spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Row(
                    [
                        ft.Text("Локальные команды:", size=11, color="#91a0b3"),
                        ft.TextButton("help", on_click=command_handler("help")),
                        ft.TextButton("clear", on_click=command_handler("clear")),
                    ],
                    spacing=2,
                ),
            ],
            spacing=13,
        )
    )

    page.add(
        ft.Container(
            content=ft.Column([header, connection_card, bulbs_card, console_card], spacing=16),
            padding=ft.Padding.symmetric(horizontal=4, vertical=6),
        )
    )

    async def initial_load() -> None:
        try:
            await request("/api/health")
            status.value = "Сервер подключён"
            status.color = "#b6e36b"
            await refresh_bulbs()
        except (RuntimeError, ValueError, KeyError) as exc:
            status.value = "Нет подключения"
            status.color = "#ff8585"
            log(f"Подключение: {exc}", "#ff8585")
        page.update()

    page.run_task(initial_load)


if __name__ == "__main__":
    ft.run(main)
