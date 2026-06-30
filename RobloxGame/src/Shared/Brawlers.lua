--[[
	Brawlers (ModuleScript)
	Lista de todos os personagens jogáveis e seus atributos.
	Para criar um brawler novo, copie um bloco e mude os valores.

	Campos:
	  DisplayName : nome que aparece na tela
	  Price       : preço em moedas (0 = grátis)
	  Health      : vida máxima
	  WalkSpeed   : velocidade de andar
	  Damage      : dano por tiro
	  Range       : alcance do tiro (studs)
	  Spread      : abertura do tiro em graus (pequeno = preciso, grande = "espingarda")
	  ReloadTime  : tempo entre tiros (segundos)
	  Color       : cor do corpo do personagem
	  Special     : habilidade especial { Damage, Range, Spread, Cooldown }

	Local no Studio: ReplicatedStorage > Shared > Brawlers
]]

local Brawlers = {

	Shelly = {
		DisplayName = "Shelly",
		Price = 0,
		Health = 100,
		WalkSpeed = 16,
		Damage = 16,
		Range = 35,
		Spread = 24,
		ReloadTime = 0.7,
		Color = Color3.fromRGB(255, 170, 60),
		Special = { Damage = 30, Range = 42, Spread = 38, Cooldown = 8 },
		-- aparência: Hat = "Cap" | "Box" | "Helmet" | "Cone"
		Skin = { Hat = "Cap", HatColor = Color3.fromRGB(180, 110, 30), Scale = 1.0 },
	},

	Colt = {
		DisplayName = "Colt",
		Price = 200,
		Health = 78,
		WalkSpeed = 16,
		Damage = 13,
		Range = 58,
		Spread = 5,
		ReloadTime = 0.3,
		Color = Color3.fromRGB(70, 130, 255),
		Special = { Damage = 22, Range = 65, Spread = 6, Cooldown = 7 },
		Skin = { Hat = "Box", HatColor = Color3.fromRGB(30, 60, 160), Scale = 0.98 },
	},

	Bull = {
		DisplayName = "Bull",
		Price = 300,
		Health = 165,
		WalkSpeed = 17,
		Damage = 24,
		Range = 24,
		Spread = 32,
		ReloadTime = 0.85,
		Color = Color3.fromRGB(120, 90, 60),
		Special = { Damage = 36, Range = 30, Spread = 40, Cooldown = 9 },
		Skin = { Hat = "Helmet", HatColor = Color3.fromRGB(70, 50, 30), Scale = 1.2 },
	},

	Piper = {
		DisplayName = "Piper",
		Price = 500,
		Health = 68,
		WalkSpeed = 16,
		Damage = 38,
		Range = 82,
		Spread = 2,
		ReloadTime = 1.2,
		Color = Color3.fromRGB(230, 80, 160),
		Special = { Damage = 50, Range = 70, Spread = 3, Cooldown = 10 },
		Skin = { Hat = "Cone", HatColor = Color3.fromRGB(170, 40, 110), Scale = 0.9 },
	},

	-- ninja ágil: cabelo espetado loiro + bandana, inspirado em ninjas de anime
	Kage = {
		DisplayName = "Kage",
		Price = 650,
		Health = 85,
		WalkSpeed = 18,
		Damage = 11,
		Range = 52,
		Spread = 7,
		ReloadTime = 0.22,
		Color = Color3.fromRGB(255, 145, 35),
		-- Especial: explosão em todas as direções (Spread 360 = atinge ao redor)
		Special = { Damage = 40, Range = 34, Spread = 360, Cooldown = 11 },
		Skin = {
			Hat = "Headband", HatColor = Color3.fromRGB(50, 80, 150),
			Hair = true, HairColor = Color3.fromRGB(255, 221, 90),
			Scale = 1.0,
		},
	},

	-- lutadora corpo a corpo: dano altíssimo bem de perto, cabelo rosa
	Punho = {
		DisplayName = "Punho",
		Price = 450,
		Health = 92,
		WalkSpeed = 17,
		Damage = 30,
		Range = 14,
		Spread = 50,
		ReloadTime = 0.55,
		Color = Color3.fromRGB(255, 110, 150),
		Special = { Damage = 55, Range = 18, Spread = 75, Cooldown = 9 },
		Skin = { Hair = true, HairColor = Color3.fromRGB(255, 140, 190), Scale = 1.0 },
	},

	-- controladora de área: especial atinge tudo ao redor, cabelo vermelho
	Areia = {
		DisplayName = "Areia",
		Price = 750,
		Health = 95,
		WalkSpeed = 15,
		Damage = 14,
		Range = 40,
		Spread = 16,
		ReloadTime = 0.6,
		Color = Color3.fromRGB(200, 90, 50),
		Special = { Damage = 26, Range = 30, Spread = 360, Cooldown = 13 },
		Skin = { Hair = true, HairColor = Color3.fromRGB(180, 40, 40), Scale = 1.05 },
	},

	-- atiradora precisa e sorrateira: máscara + bandana, cabelo prata
	Sombra = {
		DisplayName = "Sombra",
		Price = 850,
		Health = 75,
		WalkSpeed = 16,
		Damage = 34,
		Range = 75,
		Spread = 2,
		ReloadTime = 1.0,
		Color = Color3.fromRGB(70, 70, 80),
		Special = { Damage = 48, Range = 80, Spread = 2, Cooldown = 10 },
		Skin = {
			Hat = "Headband", HatColor = Color3.fromRGB(50, 50, 55),
			Hair = true, HairColor = Color3.fromRGB(190, 190, 195),
			Mask = true, MaskColor = Color3.fromRGB(40, 40, 45),
			Scale = 1.0,
		},
	},
}

return Brawlers
