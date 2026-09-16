[app]
title = Painel Discord
package.name = paineldiscord
package.domain = org.seunome

source.dir = .
source.include_exts = py,png,jpg,kv,atlas

version = 0.1

# python3==3.11.9 fixa a versao do Python usada DENTRO do app Android -
# versoes mais novas (3.13/3.14) ainda tem incompatibilidades com o Kivy.
# hostpython3 precisa ser a MESMA versao (regra do proprio python-for-android)
#
# IMPORTANTE: o processo de build do Android instala os requirements com
# "pip install --no-deps", ou seja, ele NAO baixa sozinho as dependencias
# de cada pacote. Por isso discord.py sozinho nao é suficiente - sem
# listar aiohttp/multidict/yarl/frozenlist/attrs/aiosignal aqui, o app
# compila e instala normalmente, mas fecha na hora de abrir com
# "ModuleNotFoundError: No module named 'aiohttp'". Fixamos versoes
# anteriores ao pacote "propcache" (que aiohttp passou a exigir a partir
# da 3.10 e nao tem como compilar pro Android).
# certifi e o certificado SSL usado pra resolver o erro de conexao no
# Android (ver comentario no main.py, perto do SSL_CERT_FILE)
requirements = python3==3.11.9,hostpython3==3.11.9,kivy==2.3.0,pillow,certifi,attrs==23.2.0,aiosignal==1.3.1,frozenlist==1.4.1,multidict==6.0.5,yarl==1.9.4,aiohttp==3.9.5,discord.py==2.4.0

orientation = portrait
fullscreen = 0

# Permissao de internet e necessaria pro bot conectar no Discord
android.permissions = INTERNET

# API 35 (Android 15) e o minimo que o Google Play exige atualmente
# (ate 31/08/2026). Com API 33 o Android tratava o app como "feito pra
# versao antiga", o que deixa os avisos do Play Protect mais agressivos.
android.api = 35
android.minapi = 24
android.ndk = 25b
# armeabi-v7a (32 bits) roda tanto em celular de 32 quanto de 64 bits.
# Trocado de arm64-v8a pra testar se o Galaxy A10 so aceita apps 32-bit
# (alguns modelos dessa linha tem chip 64-bit mas rodam Android so em modo
# 32-bit pra economizar RAM - nesse caso um apk arm64-v8a nao instala e o
# Android so mostra "o app nao foi instalado", sem dizer o motivo real)
android.archs = armeabi-v7a

[buildozer]
log_level = 2
warn_on_root = 1
