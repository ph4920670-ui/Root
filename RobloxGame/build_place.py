#!/usr/bin/env python3
"""
Gera um arquivo de lugar do Roblox (.rbxlx) com TODO o jogo já montado:
ReplicatedStorage/Shared, ServerScriptService e StarterPlayerScripts com
os scripts nos tipos corretos. Basta abrir o .rbxlx no Studio.
"""
import os

SRC = os.path.join(os.path.dirname(__file__), "src")
OUT = os.path.join(os.path.dirname(__file__), "BrawlArena.rbxlx")

_ref = [0]
def ref():
    _ref[0] += 1
    return f"RBX{_ref[0]}"

def read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def script_item(cls, name, source):
    # Source vai em CDATA (o codigo nao contem ']]>').
    return (
        f'<Item class="{cls}" referent="{ref()}">'
        f'<Properties>'
        f'<string name="Name">{name}</string>'
        f'<ProtectedString name="Source"><![CDATA[{source}]]></ProtectedString>'
        f'</Properties>'
        f'</Item>'
    )

def folder_item(name, children):
    return (
        f'<Item class="Folder" referent="{ref()}">'
        f'<Properties><string name="Name">{name}</string></Properties>'
        f'{"".join(children)}'
        f'</Item>'
    )

def service_item(cls, name, children):
    return (
        f'<Item class="{cls}" referent="{ref()}">'
        f'<Properties><string name="Name">{name}</string></Properties>'
        f'{"".join(children)}'
        f'</Item>'
    )

# ----- Shared (ModuleScripts) -----
shared_children = []
for fname in ["GameConfig", "Brawlers", "Maps", "Net"]:
    shared_children.append(script_item("ModuleScript", fname, read(os.path.join(SRC, "Shared", fname + ".lua"))))
replicated = service_item("ReplicatedStorage", "ReplicatedStorage", [folder_item("Shared", shared_children)])

# ----- ServerScriptService -----
server_children = []
# Main e' Script; o resto ModuleScript
server_children.append(script_item("Script", "Main", read(os.path.join(SRC, "Server", "Main.server.lua"))))
for fname in ["DataManager", "Spawner", "CombatManager", "ShopManager", "MapGenerator", "MatchManager"]:
    server_children.append(script_item("ModuleScript", fname, read(os.path.join(SRC, "Server", fname + ".lua"))))
server = service_item("ServerScriptService", "ServerScriptService", server_children)

# ----- StarterPlayer > StarterPlayerScripts > Cliente (LocalScript) -----
client_src = read(os.path.join(SRC, "StarterPlayerScripts", "Client.client.lua"))
sps = service_item("StarterPlayerScripts", "StarterPlayerScripts", [script_item("LocalScript", "Cliente", client_src)])
starter_player = service_item("StarterPlayer", "StarterPlayer", [sps])

# ----- Workspace (com um SpawnLocation simples) -----
workspace = (
    f'<Item class="Workspace" referent="{ref()}">'
    f'<Properties>'
    f'<bool name="FilteringEnabled">true</bool>'
    f'</Properties>'
    f'</Item>'
)

header = (
    '<roblox xmlns:xmime="http://www.w3.org/2005/05/xmlmime" '
    'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
    'xsi:noNamespaceSchemaLocation="http://www.roblox.com/roblox.xsd" version="4">'
)

doc = header + workspace + replicated + server + starter_player + "</roblox>"

with open(OUT, "w", encoding="utf-8") as f:
    f.write(doc)

print("OK ->", OUT, f"({len(doc)} bytes)")
