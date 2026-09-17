"""
App Android (Kivy) - Painel de Discord (v2 - visual e funcoes extras)
======================================================================
Telas: Login -> Servidores -> Canais -> Chat (+ Membros)
"""

import os
import re
import threading
import asyncio
import traceback

from kivy.app import App
from kivy.uix.screenmanager import ScreenManager, Screen, SlideTransition
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView
from kivy.uix.image import AsyncImage
from kivy.uix.widget import Widget
from kivy.uix.checkbox import CheckBox
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, RoundedRectangle
from kivy.metrics import dp
from kivy.utils import escape_markup

# Se o discord.py falhar ao carregar (biblioteca nativa incompativel, etc.),
# guardamos o erro aqui em vez de deixar o app fechar sem explicar nada.
# ERRO_IMPORT_DISCORD sendo None = tudo certo, app segue normal.
ERRO_IMPORT_DISCORD = None
try:
    import ssl
    import certifi
    import aiohttp
    import discord
    from discord import ui
    # No Android o Python nao acha sozinho os certificados SSL do sistema,
    # e qualquer conexao HTTPS/WSS (como a do discord.py com o Discord)
    # falha com um erro generico de conexao. Apontando essa variavel pro
    # certificado que vem junto com o certifi, o ssl padrao do Python passa
    # a enxergar os certificados corretamente.
    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
except Exception:
    ERRO_IMPORT_DISCORD = traceback.format_exc()
    import types
    discord = types.SimpleNamespace()
    ui = types.SimpleNamespace(View=object)

# ---------------------------------------------------------------------------
# Paleta de cores (estilo Discord dark)
# ---------------------------------------------------------------------------
BG_APP = (0.114, 0.122, 0.133, 1)        # #1D2023 fundo geral
BG_SIDEBAR = (0.145, 0.153, 0.169, 1)    # #25272B lista de servidores/canais
BG_MAIN = (0.180, 0.192, 0.212, 1)       # #2E3136 area de chat
BG_BUBBLE = (0.216, 0.224, 0.247, 1)     # #36393F bolha de mensagem
TEXT_WHITE = (0.95, 0.95, 0.95, 1)
TEXT_MUTED = (0.6, 0.62, 0.65, 1)
ACCENT = (0.345, 0.396, 0.949, 1)        # blurple #5865F2
GREEN_ONLINE = (0.227, 0.706, 0.408, 1)
YELLOW_IDLE = (0.949, 0.694, 0.192, 1)
RED_DND = (0.929, 0.263, 0.263, 1)
GRAY_OFFLINE = (0.47, 0.49, 0.52, 1)

TOKEN_FILE = "token.txt"


def rounded_bg(widget, color, radius=dp(10)):
    with widget.canvas.before:
        c = Color(*color)
        widget._bg = RoundedRectangle(pos=widget.pos, size=widget.size, radius=[radius])
    widget._bg_color = c
    widget.bind(pos=lambda w, v: setattr(w._bg, "pos", v))
    widget.bind(size=lambda w, v: setattr(w._bg, "size", v))


def flat_bg(widget, color):
    with widget.canvas.before:
        Color(*color)
        from kivy.graphics import Rectangle
        widget._bg = Rectangle(pos=widget.pos, size=widget.size)
    widget.bind(pos=lambda w, v: setattr(w._bg, "pos", v))
    widget.bind(size=lambda w, v: setattr(w._bg, "size", v))


class FlatButton(Button):
    """Botao sem a textura padrao do Kivy, com fundo arredondado customizado."""
    def __init__(self, bg_color=BG_MAIN, radius=dp(8), **kwargs):
        super().__init__(**kwargs)
        self.background_normal = ""
        self.background_down = ""
        self.background_color = (0, 0, 0, 0)
        self.color = TEXT_WHITE
        rounded_bg(self, bg_color, radius)


def build_topbar(title, on_back=None, right_widget=None):
    """Cabecalho padrao usado em Canais/Membros/Chat: botao de voltar
    circular + titulo + espaco opcional pra um widget extra a direita."""
    bar = BoxLayout(size_hint_y=None, height=dp(58), padding=(dp(10), dp(8)), spacing=dp(10))
    flat_bg(bar, BG_MAIN)

    if on_back:
        back_btn = FlatButton(text="\u2039", bg_color=BG_SIDEBAR, radius=dp(20),
                               font_size=dp(24), size_hint=(None, None), size=(dp(40), dp(40)))
        back_btn.bind(on_press=on_back)
        bar.add_widget(back_btn)

    title_label = Label(text=title, bold=True, color=TEXT_WHITE, font_size=dp(16),
                         halign="left", valign="middle", shorten=True)
    title_label.bind(size=lambda w, v: setattr(w, "text_size", v))
    bar.add_widget(title_label)

    if right_widget:
        bar.add_widget(right_widget)

    return bar


class CircleAvatar(Widget):
    """Avatar circular a partir de uma URL (usa RoundedRectangle com raio = metade do lado)."""
    def __init__(self, source="", size_px=dp(36), **kwargs):
        super().__init__(size_hint=(None, None), size=(size_px, size_px), **kwargs)
        with self.canvas:
            self._color = Color(0.25, 0.27, 0.30, 1)
            self._rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[size_px / 2])
        self.bind(pos=self._sync, size=self._sync)
        self._loader = AsyncImage(source=source or "")
        self._loader.bind(texture=self._on_texture)

    def _sync(self, *_a):
        self._rect.pos = self.pos
        self._rect.size = self.size
        self._rect.radius = [self.size[0] / 2]

    def _on_texture(self, _inst, tex):
        if tex:
            self._rect.texture = tex


def status_color(status):
    return {
        "online": GREEN_ONLINE,
        "idle": YELLOW_IDLE,
        "dnd": RED_DND,
    }.get(str(status), GRAY_OFFLINE)


def discord_md_to_kivy(texto):
    """Converte formatacao estilo Discord (#, ##, -#, **negrito**, *italico*)
    em markup do Kivy, pra exibir na nossa propria tela do jeito real."""
    linhas_convertidas = []
    for linha in (texto or "").split("\n"):
        if linha.startswith("### "):
            corpo = escape_markup(linha[4:])
            linhas_convertidas.append(f"[size=16][b]{corpo}[/b][/size]")
        elif linha.startswith("## "):
            corpo = escape_markup(linha[3:])
            linhas_convertidas.append(f"[size=19][b]{corpo}[/b][/size]")
        elif linha.startswith("# "):
            corpo = escape_markup(linha[2:])
            linhas_convertidas.append(f"[size=23][b]{corpo}[/b][/size]")
        elif linha.startswith("-# "):
            corpo = escape_markup(linha[3:])
            linhas_convertidas.append(f"[size=11][color=96989d]{corpo}[/color][/size]")
        else:
            corpo = escape_markup(linha)
            corpo = re.sub(r"\*\*(.+?)\*\*", r"[b]\1[/b]", corpo)
            corpo = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"[i]\1[/i]", corpo)
            linhas_convertidas.append(corpo)
    return "\n".join(linhas_convertidas)


class ButtonView(ui.View):
    """Cria botoes reais do Discord (o bot recebe o clique via interaction)."""
    def __init__(self, labels):
        super().__init__(timeout=None)
        for label in labels[:5]:  # discord permite ate 5 botoes por linha
            botao = ui.Button(label=label[:80], style=discord.ButtonStyle.primary)
            botao.callback = self._fazer_callback(label)
            self.add_item(botao)

    def _fazer_callback(self, label):
        async def callback(interaction):
            await interaction.response.send_message(
                f'{interaction.user.display_name} clicou em "{label}"'
            )
        return callback


def parse_input_para_envio(texto):
    """Le a sintaxe especial digitada no app:
    - %Rotulo% em qualquer parte do texto vira um botao real do Discord
    - $ ... $ (pode ter varias linhas) vira um embed real do Discord
    O resto do texto continua sendo enviado como mensagem normal
    (# / ## / -# / ** / * ja sao markdown nativo do proprio Discord).
    """
    padrao_botao = re.compile(r"%([^%]+)%")
    rotulos = padrao_botao.findall(texto)
    texto_sem_botoes = padrao_botao.sub("", texto).strip()

    embed = None
    conteudo_final = texto_sem_botoes

    padrao_embed = re.compile(r"\$(.*?)\$", re.DOTALL)
    blocos = padrao_embed.findall(texto_sem_botoes)
    if blocos:
        corpo_embed = "\n\n".join(b.strip() for b in blocos)
        embed = discord.Embed(description=corpo_embed, color=discord.Color.blurple())
        conteudo_final = padrao_embed.sub("", texto_sem_botoes).strip()

    view = ButtonView(rotulos) if rotulos else None

    return (conteudo_final or None), embed, view


# ---------------------------------------------------------------------------
# Backend do Discord
# ---------------------------------------------------------------------------
class DiscordBackend:
    def __init__(self):
        self.loop = None
        self.client = None
        self.ready = threading.Event()
        self.error_event = threading.Event()
        self.error_message = ""
        self.guilds_cache = []
        self.on_message_callback = None
        self.on_edit_callback = None
        self.on_delete_callback = None
        self.on_reaction_remove_callback = None

    def start(self, token):
        self.ready.clear()
        self.error_event.clear()
        self.error_message = ""
        self.loop = asyncio.new_event_loop()
        t = threading.Thread(target=self._run, args=(token,), daemon=True)
        t.start()

    def _run(self, token):
        asyncio.set_event_loop(self.loop)

        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        intents.messages = True
        intents.members = True      # precisa ativar "Server Members Intent" no dev portal
        intents.presences = True    # precisa ativar "Presence Intent" no dev portal

        self.client = discord.Client(intents=intents)

        # O SSL_CERT_FILE nao funcionou sozinho no Android (o OpenSSL
        # compilado pro app ignora essa variavel). Aqui a gente configura
        # na mao o "conector" que o discord.py usa por baixo dos panos,
        # tanto pra API quanto pro WebSocket, apontando pro certificado
        # do certifi - isso resolve o "CERTIFICATE_VERIFY_FAILED".
        import socket as _socket
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        self.client.http.connector = aiohttp.TCPConnector(
            ssl=ssl_context, limit=0, family=_socket.AF_INET
        )

        @self.client.event
        async def on_ready():
            self.guilds_cache = list(self.client.guilds)
            self.ready.set()

        @self.client.event
        async def on_message(message):
            if self.on_message_callback:
                self.on_message_callback(message)

        @self.client.event
        async def on_raw_message_edit(payload):
            if self.on_edit_callback:
                novo_conteudo = payload.data.get("content")
                self.on_edit_callback(payload.message_id, payload.channel_id, novo_conteudo)

        @self.client.event
        async def on_raw_message_delete(payload):
            if self.on_delete_callback:
                antigo = payload.cached_message.content if payload.cached_message else None
                self.on_delete_callback(payload.message_id, payload.channel_id, antigo)

        @self.client.event
        async def on_raw_reaction_remove(payload):
            if self.on_reaction_remove_callback:
                self.on_reaction_remove_callback(payload.message_id, payload.channel_id, str(payload.emoji))

        try:
            self.loop.run_until_complete(self.client.start(token))
        except discord.LoginFailure:
            self.error_message = "Token invalido. Confira o token do bot e tente de novo."
            self.error_event.set()
        except discord.PrivilegedIntentsRequired:
            self.error_message = (
                "Faltam permissoes ativar no bot. Va no Discord Developer "
                "Portal > sua aplicacao > Bot, e ative:\n"
                "PRESENCE INTENT, SERVER MEMBERS INTENT e "
                "MESSAGE CONTENT INTENT. Depois tente conectar de novo."
            )
            self.error_event.set()
        except Exception as e:
            print("Erro ao conectar bot:", repr(e))
            self.error_message = (
                "Nao foi possivel conectar.\n"
                f"Detalhe tecnico: {type(e).__name__}: {e}"
            )
            self.error_event.set()

    def run_coro(self, coro, timeout=15):
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        return future.result(timeout=timeout)

    def get_guilds(self):
        return self.guilds_cache

    def get_text_channels(self, guild_id):
        guild = discord.utils.get(self.guilds_cache, id=guild_id)
        if not guild:
            return []
        return [c for c in guild.channels if isinstance(c, discord.TextChannel)]

    def get_members(self, guild_id):
        guild = discord.utils.get(self.guilds_cache, id=guild_id)
        if not guild:
            return []
        membros = list(guild.members)
        ordem = {"online": 0, "idle": 1, "dnd": 2, "offline": 3}
        membros.sort(key=lambda m: ordem.get(str(m.status), 3))
        return membros

    def get_channel(self, channel_id):
        return self.client.get_channel(channel_id)

    def fetch_messages(self, channel_id, limit=30):
        channel = self.get_channel(channel_id)

        async def _fetch():
            msgs = [m async for m in channel.history(limit=limit)]
            return list(reversed(msgs))

        return self.run_coro(_fetch())

    def send_message(self, channel_id, content=None, embed=None, view=None, reply_to=None):
        channel = self.get_channel(channel_id)

        async def _send():
            kwargs = {}
            if content:
                kwargs["content"] = content
            if embed:
                kwargs["embed"] = embed
            if view:
                kwargs["view"] = view
            if reply_to:
                try:
                    kwargs["reference"] = await channel.fetch_message(reply_to)
                except Exception:
                    pass
            await channel.send(**kwargs)

        return self.run_coro(_send())


backend = DiscordBackend()


# ---------------------------------------------------------------------------
# Tela de Login
# ---------------------------------------------------------------------------
class LoginScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        outer = BoxLayout(orientation="vertical")
        flat_bg(outer, BG_APP)

        # Cartao central com o formulario, nao ocupa a tela inteira
        card_wrap = BoxLayout(orientation="vertical", padding=dp(28), spacing=dp(16))
        card_wrap.add_widget(Widget(size_hint_y=1))

        card = BoxLayout(orientation="vertical", padding=dp(24), spacing=dp(12),
                          size_hint_y=None, height=dp(440))
        rounded_bg(card, BG_SIDEBAR, radius=dp(18))

        # Selo redondo com as iniciais do app (identidade propria, nao o logo do Discord)
        from kivy.uix.floatlayout import FloatLayout
        badge_wrap = BoxLayout(size_hint_y=None, height=dp(64))
        badge_holder = FloatLayout(size_hint=(None, None), size=(dp(64), dp(64)),
                                    pos_hint={"center_x": 0.5})
        badge = Widget(size_hint=(None, None), size=(dp(64), dp(64)),
                        pos_hint={"center_x": 0.5, "center_y": 0.5})
        with badge.canvas:
            Color(*ACCENT)
            badge._circle = RoundedRectangle(pos=badge.pos, size=badge.size, radius=[dp(32)])
        badge.bind(pos=lambda w, v: setattr(w._circle, "pos", v))
        badge_label = Label(text="PD", bold=True, font_size=dp(22), color=TEXT_WHITE,
                             pos_hint={"center_x": 0.5, "center_y": 0.5})
        badge_holder.add_widget(badge)
        badge_holder.add_widget(badge_label)
        badge_wrap.add_widget(Widget())
        badge_wrap.add_widget(badge_holder)
        badge_wrap.add_widget(Widget())

        title = Label(text="Painel Discord", font_size=dp(24), bold=True,
                      color=TEXT_WHITE, size_hint_y=None, height=dp(34))
        subtitle = Label(text="Painel de controle para o seu bot",
                          color=TEXT_MUTED, font_size=dp(13),
                          size_hint_y=None, height=dp(22))

        token_label = Label(text="Token do bot", color=TEXT_MUTED, font_size=dp(12),
                             halign="left", size_hint_y=None, height=dp(18))
        token_label.bind(size=lambda w, v: setattr(w, "text_size", v))

        instrucao_token = Label(
            text=("Como pegar: discord.com/developers/applications > sua "
                  "aplicacao > Bot > Reset Token (ou Copy, se ja existir um)"),
            color=TEXT_MUTED, font_size=dp(11), halign="left", valign="top",
            size_hint_y=None)
        instrucao_token.bind(
            width=lambda w, v: setattr(w, "text_size", (v, None)),
            texture_size=lambda w, v: setattr(w, "height", v[1]))

        input_wrap = BoxLayout(size_hint_y=None, height=dp(48), padding=(dp(2), dp(2)))
        rounded_bg(input_wrap, BG_MAIN, radius=dp(10))
        self.token_input = TextInput(
            hint_text="Cole o token aqui", multiline=False, password=True,
            background_color=(0, 0, 0, 0), foreground_color=TEXT_WHITE,
            cursor_color=ACCENT, padding=(dp(12), dp(12)),
            background_normal="", background_active=""
        )
        input_wrap.add_widget(self.token_input)

        salvar_box = BoxLayout(size_hint_y=None, height=dp(32), spacing=dp(8))
        self.salvar_check = CheckBox(size_hint_x=None, width=dp(28))
        salvar_box.add_widget(self.salvar_check)
        salvar_box.add_widget(Label(text="Salvar token neste aparelho",
                                     color=TEXT_MUTED, font_size=dp(13)))

        self.status_label = Label(text="", color=TEXT_MUTED, font_size=dp(12),
                                   size_hint_y=None, height=dp(24), halign="center")
        self.status_label.bind(
            width=lambda w, v: setattr(w, "text_size", (v, None)),
            texture_size=lambda w, v: setattr(w, "height", max(dp(24), v[1])))

        self.connect_btn = FlatButton(text="Conectar", bg_color=ACCENT,
                                       size_hint_y=None, height=dp(48))
        self.connect_btn.bind(on_press=self.conectar)

        card.add_widget(badge_wrap)
        card.add_widget(title)
        card.add_widget(subtitle)
        card.add_widget(token_label)
        card.add_widget(instrucao_token)
        card.add_widget(input_wrap)
        card.add_widget(salvar_box)
        card.add_widget(self.connect_btn)
        card.add_widget(self.status_label)

        card_wrap.add_widget(card)
        card_wrap.add_widget(Widget(size_hint_y=1))
        outer.add_widget(card_wrap)
        self.add_widget(outer)

    def on_pre_enter(self):
        caminho = os.path.join(App.get_running_app().user_data_dir, TOKEN_FILE)
        if os.path.exists(caminho):
            with open(caminho, "r") as f:
                self.token_input.text = f.read().strip()
            self.salvar_check.active = True

    def conectar(self, *_):
        token = self.token_input.text.strip()
        if not token:
            self.status_label.text = "Cole um token valido."
            self.status_label.color = RED_DND
            return

        if self.salvar_check.active:
            caminho = os.path.join(App.get_running_app().user_data_dir, TOKEN_FILE)
            with open(caminho, "w") as f:
                f.write(token)
        else:
            caminho = os.path.join(App.get_running_app().user_data_dir, TOKEN_FILE)
            if os.path.exists(caminho):
                os.remove(caminho)

        self.status_label.text = "Conectando..."
        self.status_label.color = TEXT_MUTED
        self.connect_btn.disabled = True
        self._tentativas = 0
        backend.start(token)
        Clock.schedule_interval(self.checar_conexao, 0.5)

    def checar_conexao(self, _dt):
        self._tentativas += 1

        if backend.ready.is_set():
            self.status_label.text = "Conectado!"
            self.status_label.color = GREEN_ONLINE
            self.manager.transition = SlideTransition(direction="left", duration=0.3)
            self.manager.current = "servidores"
            self.connect_btn.disabled = False
            return False

        if backend.error_event.is_set():
            self.status_label.text = backend.error_message
            self.status_label.color = RED_DND
            self.connect_btn.disabled = False
            return False

        # Tempo esgotado (20s) sem conectar nem dar erro explicito
        if self._tentativas >= 40:
            self.status_label.text = "Tempo esgotado. Verifique sua internet e tente de novo."
            self.status_label.color = RED_DND
            self.connect_btn.disabled = False
            return False


# ---------------------------------------------------------------------------
# Tela de Servidores
# ---------------------------------------------------------------------------
class ServidoresScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.root_box = BoxLayout(orientation="vertical")
        flat_bg(self.root_box, BG_SIDEBAR)
        self.add_widget(self.root_box)

    def on_enter(self):
        self.root_box.clear_widgets()

        header = BoxLayout(size_hint_y=None, height=dp(58), padding=(dp(20), 0))
        flat_bg(header, BG_MAIN)
        titulo = Label(text="Servidores", bold=True, color=TEXT_WHITE, font_size=dp(18),
                        halign="left", valign="middle")
        titulo.bind(size=lambda w, v: setattr(w, "text_size", v))
        header.add_widget(titulo)
        self.root_box.add_widget(header)

        scroll = ScrollView()
        lista = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(10), padding=dp(14))
        lista.bind(minimum_height=lista.setter("height"))

        for guild in backend.get_guilds():
            item = BoxLayout(size_hint_y=None, height=dp(64), spacing=dp(14), padding=(dp(12), 0))
            rounded_bg(item, BG_MAIN, radius=dp(14))
            icon_url = guild.icon.url if guild.icon else ""
            item.add_widget(CircleAvatar(source=icon_url, size_px=dp(44)))
            info = BoxLayout(orientation="vertical", spacing=dp(2))
            info.add_widget(Label(text=guild.name, color=TEXT_WHITE, bold=True, font_size=dp(15),
                                   halign="left", valign="bottom", shorten=True))
            info.add_widget(Label(text=f"{guild.member_count} membros", color=TEXT_MUTED,
                                   halign="left", valign="top", font_size=dp(12)))
            for lbl in info.children:
                lbl.bind(size=lambda w, v: setattr(w, "text_size", v))
            item.add_widget(info)
            item.add_widget(Label(text="\u203a", color=TEXT_MUTED, font_size=dp(20),
                                   size_hint_x=None, width=dp(20)))

            btn_overlay = Button(background_color=(0, 0, 0, 0), background_normal="")
            btn_overlay.bind(on_press=lambda inst, g=guild: self.abrir_servidor(g))
            item.add_widget(btn_overlay)

            lista.add_widget(item)

        scroll.add_widget(lista)
        self.root_box.add_widget(scroll)

    def abrir_servidor(self, guild):
        app = App.get_running_app()
        app.selected_guild = guild
        self.manager.transition = SlideTransition(direction="left", duration=0.28)
        self.manager.current = "canais"


# ---------------------------------------------------------------------------
# Tela de Canais
# ---------------------------------------------------------------------------
class CanaisScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.root_box = BoxLayout(orientation="vertical")
        flat_bg(self.root_box, BG_SIDEBAR)
        self.add_widget(self.root_box)

    def on_enter(self):
        self.root_box.clear_widgets()
        app = App.get_running_app()
        guild = app.selected_guild

        membros_btn = FlatButton(text="Membros", bg_color=ACCENT, radius=dp(14),
                                  font_size=dp(13), size_hint=(None, None),
                                  size=(dp(96), dp(36)))
        membros_btn.bind(on_press=self.abrir_membros)
        self.root_box.add_widget(build_topbar(
            guild.name if guild else "", on_back=self.voltar, right_widget=membros_btn))

        scroll = ScrollView()
        lista = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(8), padding=dp(14))
        lista.bind(minimum_height=lista.setter("height"))

        for canal in backend.get_text_channels(guild.id):
            item = BoxLayout(size_hint_y=None, height=dp(52), spacing=dp(12), padding=(dp(12), 0))
            rounded_bg(item, BG_MAIN, radius=dp(12))

            badge = Label(text="#", bold=True, color=ACCENT, font_size=dp(16),
                          size_hint=(None, None), size=(dp(30), dp(30)))
            rounded_bg(badge, BG_SIDEBAR, radius=dp(15))
            item.add_widget(badge)

            nome = Label(text=canal.name, color=TEXT_WHITE, font_size=dp(14),
                        halign="left", valign="middle", shorten=True)
            nome.bind(size=lambda w, v: setattr(w, "text_size", v))
            item.add_widget(nome)

            btn_overlay = Button(background_color=(0, 0, 0, 0), background_normal="")
            btn_overlay.bind(on_press=lambda inst, c=canal: self.abrir_canal(c))
            item.add_widget(btn_overlay)

            lista.add_widget(item)

        scroll.add_widget(lista)
        self.root_box.add_widget(scroll)

    def abrir_canal(self, canal):
        app = App.get_running_app()
        app.selected_channel = canal
        self.manager.transition = SlideTransition(direction="left", duration=0.28)
        self.manager.current = "chat"

    def abrir_membros(self, *_):
        self.manager.transition = SlideTransition(direction="left", duration=0.28)
        self.manager.current = "membros"

    def voltar(self, *_):
        self.manager.transition = SlideTransition(direction="right", duration=0.28)
        self.manager.current = "servidores"


# ---------------------------------------------------------------------------
# Tela de Membros
# ---------------------------------------------------------------------------
class MembrosScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.root_box = BoxLayout(orientation="vertical")
        flat_bg(self.root_box, BG_SIDEBAR)
        self.add_widget(self.root_box)

    def on_enter(self):
        self.root_box.clear_widgets()
        app = App.get_running_app()
        guild = app.selected_guild

        self.root_box.add_widget(build_topbar("Membros", on_back=self.voltar))

        scroll = ScrollView()
        lista = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(8), padding=dp(14))
        lista.bind(minimum_height=lista.setter("height"))

        for membro in backend.get_members(guild.id):
            item = BoxLayout(size_hint_y=None, height=dp(58), spacing=dp(12), padding=(dp(12), 0))
            rounded_bg(item, BG_MAIN, radius=dp(12))

            avatar_box = BoxLayout(size_hint=(None, None), size=(dp(58), dp(40)), spacing=dp(5))
            avatar_box.add_widget(CircleAvatar(source=membro.display_avatar.url, size_px=dp(40)))
            dot = Widget(size_hint=(None, None), size=(dp(13), dp(13)))
            with dot.canvas:
                Color(*BG_MAIN)
                from kivy.graphics import Ellipse
                dot._ring = Ellipse(pos=dot.pos, size=dot.size)
                Color(*status_color(membro.status))
                dot._el = Ellipse(pos=(dot.pos[0] + dp(1.5), dot.pos[1] + dp(1.5)),
                                   size=(dot.size[0] - dp(3), dot.size[1] - dp(3)))
            def _sync_dot(w, v, dot=dot):
                dot._ring.pos = dot.pos
                dot._ring.size = dot.size
                dot._el.pos = (dot.pos[0] + dp(1.5), dot.pos[1] + dp(1.5))
                dot._el.size = (dot.size[0] - dp(3), dot.size[1] - dp(3))
            dot.bind(pos=_sync_dot)
            avatar_box.add_widget(dot)

            info = BoxLayout(orientation="vertical", spacing=dp(2))
            nome = Label(text=membro.display_name, color=TEXT_WHITE, font_size=dp(14),
                        bold=True, halign="left", valign="bottom")
            status_lbl = Label(text=str(membro.status).capitalize(), color=TEXT_MUTED,
                               font_size=dp(11), halign="left", valign="top")
            for lbl in (nome, status_lbl):
                lbl.bind(size=lambda w, v: setattr(w, "text_size", v))
            info.add_widget(nome)
            info.add_widget(status_lbl)

            item.add_widget(avatar_box)
            item.add_widget(info)
            lista.add_widget(item)

        scroll.add_widget(lista)
        self.root_box.add_widget(scroll)

    def voltar(self, *_):
        self.manager.transition = SlideTransition(direction="right", duration=0.28)
        self.manager.current = "canais"


# ---------------------------------------------------------------------------
# Tela de Chat
# ---------------------------------------------------------------------------
class ChatScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.root_box = BoxLayout(orientation="vertical")
        flat_bg(self.root_box, BG_MAIN)
        self.add_widget(self.root_box)
        self.mensagens_box = None
        self.reply_target = None
        self.reply_bar = None
        self.message_widgets = {}

    def on_enter(self):
        self.root_box.clear_widgets()
        self.reply_target = None
        app = App.get_running_app()
        canal = app.selected_channel

        self.root_box.add_widget(build_topbar(f"#  {canal.name}", on_back=self.voltar))

        self.scroll = ScrollView()
        self.mensagens_box = BoxLayout(orientation="vertical", size_hint_y=None,
                                        spacing=dp(14), padding=dp(12))
        self.mensagens_box.bind(minimum_height=self.mensagens_box.setter("height"))
        self.scroll.add_widget(self.mensagens_box)
        self.root_box.add_widget(self.scroll)

        self.reply_bar_holder = BoxLayout(size_hint_y=None, height=0)
        self.root_box.add_widget(self.reply_bar_holder)

        rodape = BoxLayout(size_hint_y=None, height=dp(64), spacing=dp(10),
                            padding=(dp(10), dp(8)))
        input_wrap = BoxLayout(padding=(dp(4), dp(4)))
        rounded_bg(input_wrap, BG_BUBBLE, radius=dp(22))
        self.input_msg = TextInput(hint_text="Digite uma mensagem...", multiline=False,
                                    background_color=(0, 0, 0, 0), foreground_color=TEXT_WHITE,
                                    cursor_color=ACCENT, padding=(dp(16), dp(13)),
                                    background_normal="", background_active="")
        input_wrap.add_widget(self.input_msg)
        rodape.add_widget(input_wrap)

        enviar_btn = FlatButton(text="\u27a4", bg_color=ACCENT, radius=dp(24),
                                 font_size=dp(18), size_hint=(None, None), size=(dp(48), dp(48)))
        enviar_btn.bind(on_press=self.enviar)
        rodape.add_widget(enviar_btn)
        self.root_box.add_widget(rodape)

        self.message_widgets = {}
        threading.Thread(target=self.carregar_mensagens, args=(canal.id,), daemon=True).start()
        backend.on_message_callback = self.nova_mensagem_ao_vivo
        backend.on_edit_callback = self.mensagem_editada_evento
        backend.on_delete_callback = self.mensagem_apagada_evento
        backend.on_reaction_remove_callback = self.reacao_removida_evento

    def carregar_mensagens(self, channel_id):
        try:
            msgs = backend.fetch_messages(channel_id)
        except Exception as e:
            print("Erro ao buscar mensagens:", e)
            return
        Clock.schedule_once(lambda dt: self.popular_mensagens(msgs))

    def popular_mensagens(self, msgs):
        for m in msgs:
            self.adicionar_bolha(m)

    def nova_mensagem_ao_vivo(self, message):
        app = App.get_running_app()
        if not app.selected_channel or message.channel.id != app.selected_channel.id:
            return
        Clock.schedule_once(lambda dt: self.adicionar_bolha(message))

    def adicionar_bolha(self, message):
        linha = BoxLayout(size_hint_y=None, spacing=dp(10))
        avatar_url = message.author.display_avatar.url if hasattr(message.author, "display_avatar") else ""
        avatar_holder = BoxLayout(size_hint=(None, 1), width=dp(40))
        avatar_holder.add_widget(CircleAvatar(source=avatar_url, size_px=dp(36)))
        linha.add_widget(avatar_holder)

        conteudo = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(3))
        conteudo.bind(minimum_height=conteudo.setter("height"))

        if message.reference is not None:
            resp = Label(text="\u21aa em resposta a uma mensagem", color=TEXT_MUTED,
                         font_size=dp(11), size_hint_y=None, height=dp(16),
                         halign="left", valign="middle")
            resp.bind(size=lambda w, v: setattr(w, "text_size", v))
            conteudo.add_widget(resp)

        cabecalho = BoxLayout(size_hint_y=None, height=dp(18), spacing=dp(8))
        nome = Label(text=message.author.display_name, bold=True, color=ACCENT,
                     size_hint_x=None, halign="left", valign="middle", font_size=dp(13))
        nome.bind(texture_size=lambda w, v: setattr(w, "width", v[0]))
        hora = Label(text=message.created_at.strftime("%d/%m %H:%M"), color=TEXT_MUTED,
                     font_size=dp(11), halign="left", valign="middle")
        hora.bind(size=lambda w, v: setattr(w, "text_size", v))
        cabecalho.add_widget(nome)
        cabecalho.add_widget(hora)
        conteudo.add_widget(cabecalho)

        # linha pequena (estilo "-#" subtexto do Discord) usada quando a
        # mensagem for editada - comeca vazia/sem altura
        editado_label = Label(text="", markup=True, color=TEXT_MUTED, font_size=dp(12),
                               size_hint_y=None, height=0, halign="left", valign="top")
        editado_label.bind(width=lambda w, v: setattr(w, "text_size", (w.width, None)))
        conteudo.add_widget(editado_label)

        corpo = Label(text=discord_md_to_kivy(message.content), markup=True, color=TEXT_WHITE,
                      size_hint_y=None, halign="left", valign="top")
        corpo.bind(width=lambda w, v: setattr(w, "text_size", (w.width, None)))
        corpo.bind(texture_size=lambda w, v: setattr(w, "height", v[1]))
        conteudo.add_widget(corpo)

        for emb in message.embeds:
            caixa_embed = BoxLayout(orientation="vertical", size_hint_y=None,
                                     padding=(dp(10), dp(8)), spacing=dp(4))
            rounded_bg(caixa_embed, (0.15, 0.16, 0.19, 1), radius=dp(6))
            if emb.title:
                titulo_embed = Label(text=escape_markup(emb.title), markup=True, bold=True,
                                      color=TEXT_WHITE, size_hint_y=None, halign="left", valign="top")
                titulo_embed.bind(width=lambda w, v: setattr(w, "text_size", (w.width, None)))
                titulo_embed.bind(texture_size=lambda w, v: setattr(w, "height", v[1]))
                caixa_embed.add_widget(titulo_embed)
            if emb.description:
                desc_embed = Label(text=discord_md_to_kivy(emb.description), markup=True,
                                    color=TEXT_WHITE, size_hint_y=None, halign="left", valign="top")
                desc_embed.bind(width=lambda w, v: setattr(w, "text_size", (w.width, None)))
                desc_embed.bind(texture_size=lambda w, v: setattr(w, "height", v[1]))
                caixa_embed.add_widget(desc_embed)
            caixa_embed.bind(minimum_height=caixa_embed.setter("height"))
            conteudo.add_widget(caixa_embed)

        if message.components:
            rotulos_botoes = [
                item.label for linha in message.components for item in linha.children
                if getattr(item, "label", None)
            ]
            if rotulos_botoes:
                botoes_row = BoxLayout(size_hint_y=None, height=dp(28), spacing=dp(6))
                for rot in rotulos_botoes[:5]:
                    pill = Label(text=rot, color=ACCENT, font_size=dp(12),
                                 size_hint=(None, None), size=(dp(90), dp(26)))
                    rounded_bg(pill, BG_BUBBLE, radius=dp(8))
                    botoes_row.add_widget(pill)
                aviso = Label(text="(botoes reais - so clicaveis no Discord)", font_size=dp(10),
                              color=TEXT_MUTED, size_hint_y=None, height=dp(14))
                conteudo.add_widget(botoes_row)
                conteudo.add_widget(aviso)

        for anexo in message.attachments:
            if anexo.content_type and anexo.content_type.startswith("image"):
                img = AsyncImage(source=anexo.url, size_hint_y=None, height=dp(160),
                                  allow_stretch=True, keep_ratio=True)
                conteudo.add_widget(img)

        reaction_chips = {}
        if message.reactions:
            reacoes = BoxLayout(size_hint_y=None, height=dp(24), spacing=dp(6))
            for r in message.reactions:
                chip = Label(text=f"{r.emoji} {r.count}", color=TEXT_WHITE, font_size=dp(12),
                            size_hint=(None, None), size=(dp(50), dp(22)))
                rounded_bg(chip, BG_BUBBLE, radius=dp(10))
                reacoes.add_widget(chip)
                reaction_chips[str(r.emoji)] = chip
            conteudo.add_widget(reacoes)

        responder_btn = FlatButton(text="Responder", bg_color=BG_BUBBLE, font_size=dp(11),
                                    size_hint=(None, None), size=(dp(80), dp(22)))
        responder_btn.bind(on_press=lambda inst, m=message: self.marcar_resposta(m))
        conteudo.add_widget(responder_btn)

        conteudo.bind(minimum_height=conteudo.setter("height"))
        linha.add_widget(conteudo)
        linha.bind(minimum_height=lambda w, v: setattr(w, "height", v))
        linha.height = conteudo.height if conteudo.height > dp(40) else dp(40)
        conteudo.bind(height=lambda w, v: setattr(linha, "height", max(v, dp(40))))

        self.mensagens_box.add_widget(linha)

        self.message_widgets[message.id] = {
            "corpo_label": corpo,
            "editado_label": editado_label,
            "conteudo_atual": message.content,
            "reaction_chips": reaction_chips,
            "apagada": False,
        }

    # -------------------- edicao / exclusao / reacoes --------------------

    def mensagem_editada_evento(self, message_id, channel_id, novo_conteudo):
        app = App.get_running_app()
        if not app.selected_channel or channel_id != app.selected_channel.id:
            return
        Clock.schedule_once(lambda dt: self.aplicar_edicao(message_id, novo_conteudo))

    def aplicar_edicao(self, message_id, novo_conteudo):
        dados = self.message_widgets.get(message_id)
        if not dados or novo_conteudo is None or dados["apagada"]:
            return
        antigo = dados["conteudo_atual"]
        # mensagem nova em cima, em texto pequeno e acinzentado (estilo -# do Discord)
        dados["editado_label"].text = f"[size=12][color=96989d]{novo_conteudo}[/color][/size]"
        dados["editado_label"].texture_update()
        dados["editado_label"].height = dados["editado_label"].texture_size[1] + dp(4)
        # mensagem original embaixo, com "(editado)" pequeno no final
        dados["corpo_label"].text = f"{antigo}  [size=11][color=96989d](editado)[/color][/size]"
        dados["conteudo_atual"] = novo_conteudo

    def mensagem_apagada_evento(self, message_id, channel_id, conteudo_cache):
        app = App.get_running_app()
        if not app.selected_channel or channel_id != app.selected_channel.id:
            return
        Clock.schedule_once(lambda dt: self.aplicar_delecao(message_id, conteudo_cache))

    def aplicar_delecao(self, message_id, conteudo_cache):
        dados = self.message_widgets.get(message_id)
        if not dados:
            return
        dados["apagada"] = True
        texto_atual = dados["conteudo_atual"] or conteudo_cache or ""
        dados["corpo_label"].text = (
            f"[color=ed4245]{texto_atual}[/color]  [size=11][color=ed4245](mensagem apagada)[/color][/size]"
        )
        if dados["editado_label"].text:
            dados["editado_label"].text = f"[size=12][color=ed4245]{dados['conteudo_atual']}[/color][/size]"

    def reacao_removida_evento(self, message_id, channel_id, emoji_str):
        app = App.get_running_app()
        if not app.selected_channel or channel_id != app.selected_channel.id:
            return
        Clock.schedule_once(lambda dt: self.aplicar_remocao_reacao(message_id, emoji_str))

    def aplicar_remocao_reacao(self, message_id, emoji_str):
        dados = self.message_widgets.get(message_id)
        if not dados:
            return
        chip = dados["reaction_chips"].get(emoji_str)
        if chip:
            chip.text = f"{emoji_str} removida"
            chip.color = RED_DND
            chip._bg_color.rgba = (0.32, 0.16, 0.16, 1)

    def marcar_resposta(self, message):
        self.reply_target = message
        self.reply_bar_holder.clear_widgets()
        self.reply_bar_holder.height = dp(40)
        self.reply_bar_holder.padding = (dp(12), dp(4))
        barra = BoxLayout(size_hint_y=None, height=dp(32), padding=(dp(12), dp(4)), spacing=dp(8))
        rounded_bg(barra, BG_BUBBLE, radius=dp(10))
        texto = (message.content[:40] + "...") if len(message.content) > 40 else message.content
        resp_lbl = Label(text=f"\u21aa Respondendo a {message.author.display_name}: {texto}",
                         color=TEXT_MUTED, font_size=dp(12), halign="left", valign="middle",
                         shorten=True)
        resp_lbl.bind(size=lambda w, v: setattr(w, "text_size", v))
        barra.add_widget(resp_lbl)
        cancelar = FlatButton(text="\u2715", bg_color=BG_MAIN, radius=dp(12), font_size=dp(12),
                              size_hint=(None, None), size=(dp(24), dp(24)))
        cancelar.bind(on_press=self.cancelar_resposta)
        barra.add_widget(cancelar)
        self.reply_bar_holder.add_widget(barra)

    def cancelar_resposta(self, *_):
        self.reply_target = None
        self.reply_bar_holder.clear_widgets()
        self.reply_bar_holder.height = 0
        self.reply_bar_holder.padding = (0, 0)

    def enviar(self, *_):
        texto = self.input_msg.text.strip()
        if not texto:
            return
        app = App.get_running_app()
        canal_id = app.selected_channel.id
        reply_id = self.reply_target.id if self.reply_target else None
        self.input_msg.text = ""
        self.cancelar_resposta()

        conteudo, embed, view = parse_input_para_envio(texto)

        def _send():
            try:
                backend.send_message(canal_id, content=conteudo, embed=embed, view=view, reply_to=reply_id)
            except Exception as e:
                print("Erro ao enviar:", e)

        threading.Thread(target=_send, daemon=True).start()

    def voltar(self, *_):
        backend.on_message_callback = None
        backend.on_edit_callback = None
        backend.on_delete_callback = None
        backend.on_reaction_remove_callback = None
        self.manager.transition = SlideTransition(direction="right", duration=0.28)
        self.manager.current = "canais"


# ---------------------------------------------------------------------------
# App principal
# ---------------------------------------------------------------------------
class PainelDiscordApp(App):
    selected_guild = None
    selected_channel = None

    def build(self):
        Window.clearcolor = BG_APP
        sm = ScreenManager()
        sm.add_widget(LoginScreen(name="login"))
        sm.add_widget(ServidoresScreen(name="servidores"))
        sm.add_widget(CanaisScreen(name="canais"))
        sm.add_widget(MembrosScreen(name="membros"))
        sm.add_widget(ChatScreen(name="chat"))
        return sm


class ErroInicializacaoApp(App):
    """Tela simples mostrada quando o app nao consegue nem carregar o
    discord.py - assim da pra ler o motivo direto na tela do celular,
    sem precisar de cabo USB nem app de log."""
    def build(self):
        Window.clearcolor = BG_APP
        root = BoxLayout(orientation="vertical", padding=dp(20), spacing=dp(12))
        flat_bg(root, BG_APP)

        titulo = Label(text="Nao foi possivel iniciar o app",
                        bold=True, font_size=dp(18), color=RED_DND,
                        size_hint_y=None, height=dp(40))
        subtitulo = Label(
            text="Tire um print desta tela e mande pra quem esta te ajudando:",
            color=TEXT_MUTED, font_size=dp(13), size_hint_y=None, height=dp(50),
            halign="left")
        subtitulo.bind(size=lambda w, v: setattr(w, "text_size", v))

        scroll = ScrollView()
        erro_label = Label(
            text=ERRO_IMPORT_DISCORD or "(erro desconhecido)",
            color=TEXT_WHITE, font_size=dp(12), size_hint_y=None,
            halign="left", valign="top")
        erro_label.bind(
            width=lambda w, v: setattr(w, "text_size", (v, None)),
            texture_size=lambda w, v: setattr(w, "height", v[1]))
        scroll.add_widget(erro_label)

        root.add_widget(titulo)
        root.add_widget(subtitulo)
        root.add_widget(scroll)
        return root


if __name__ == "__main__":
    if ERRO_IMPORT_DISCORD:
        ErroInicializacaoApp().run()
    else:
        PainelDiscordApp().run()
