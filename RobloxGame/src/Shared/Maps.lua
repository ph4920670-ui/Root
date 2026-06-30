--[[
	Maps (ModuleScript)
	Definição dos 3 mapas. Os mapas são CONSTRUÍDOS POR CÓDIGO (não precisa
	montar nada à mão no Studio). Cada mapa tem chão, paredes em volta,
	obstáculos pra se proteger e pontos de nascimento.

	Tudo é centrado na posição (0,0,0). O topo do chão fica em y = 0.

	Campos:
	  Name          : nome do mapa
	  Size          : tamanho do chão (largura, _, comprimento)
	  FloorColor    : cor do chão
	  ObstacleColor : cor dos obstáculos
	  Material      : material do chão
	  Obstacles     : lista de blocos { Pos = Vector3, Size = Vector3 }  (Pos.Y é a base, no nível do chão)
	  SpawnPoints   : lista de Vector3 onde os jogadores nascem (y ~ 4)

	Local no Studio: ReplicatedStorage > Shared > Maps
]]

local Maps = {

	-- ===================== MAPA 1 =====================
	{
		Name = "Arena Clássica",
		Size = Vector3.new(100, 1, 100),
		FloorColor = Color3.fromRGB(95, 160, 90),
		ObstacleColor = Color3.fromRGB(120, 85, 60),
		Material = Enum.Material.Grass,
		Obstacles = {
			{ Pos = Vector3.new(0, 0, 0),    Size = Vector3.new(10, 10, 10) },
			{ Pos = Vector3.new(25, 0, 25),  Size = Vector3.new(8, 8, 8) },
			{ Pos = Vector3.new(-25, 0, 25), Size = Vector3.new(8, 8, 8) },
			{ Pos = Vector3.new(25, 0, -25), Size = Vector3.new(8, 8, 8) },
			{ Pos = Vector3.new(-25, 0, -25),Size = Vector3.new(8, 8, 8) },
			{ Pos = Vector3.new(0, 0, 35),   Size = Vector3.new(20, 6, 4) },
			{ Pos = Vector3.new(0, 0, -35),  Size = Vector3.new(20, 6, 4) },
		},
		SpawnPoints = {
			Vector3.new(-40, 4, -40), Vector3.new(40, 4, 40),
			Vector3.new(-40, 4, 40),  Vector3.new(40, 4, -40),
			Vector3.new(0, 4, -42),   Vector3.new(0, 4, 42),
			Vector3.new(-42, 4, 0),   Vector3.new(42, 4, 0),
		},
	},

	-- ===================== MAPA 2 =====================
	{
		Name = "Labirinto",
		Size = Vector3.new(120, 1, 120),
		FloorColor = Color3.fromRGB(110, 110, 125),
		ObstacleColor = Color3.fromRGB(60, 60, 75),
		Material = Enum.Material.Slate,
		Obstacles = {
			{ Pos = Vector3.new(-30, 0, -30), Size = Vector3.new(6, 9, 28) },
			{ Pos = Vector3.new(30, 0, 30),   Size = Vector3.new(6, 9, 28) },
			{ Pos = Vector3.new(-30, 0, 30),  Size = Vector3.new(28, 9, 6) },
			{ Pos = Vector3.new(30, 0, -30),  Size = Vector3.new(28, 9, 6) },
			{ Pos = Vector3.new(0, 0, 0),     Size = Vector3.new(14, 9, 14) },
			{ Pos = Vector3.new(0, 0, 45),    Size = Vector3.new(6, 9, 22) },
			{ Pos = Vector3.new(0, 0, -45),   Size = Vector3.new(6, 9, 22) },
		},
		SpawnPoints = {
			Vector3.new(-50, 4, -50), Vector3.new(50, 4, 50),
			Vector3.new(-50, 4, 50),  Vector3.new(50, 4, -50),
			Vector3.new(0, 4, -52),   Vector3.new(0, 4, 52),
			Vector3.new(-52, 4, 0),   Vector3.new(52, 4, 0),
		},
	},

	-- ===================== MAPA 3 =====================
	{
		Name = "Deserto",
		Size = Vector3.new(90, 1, 90),
		FloorColor = Color3.fromRGB(225, 195, 130),
		ObstacleColor = Color3.fromRGB(170, 130, 80),
		Material = Enum.Material.Sand,
		Obstacles = {
			{ Pos = Vector3.new(0, 0, 0),     Size = Vector3.new(12, 7, 12) },
			{ Pos = Vector3.new(20, 0, 0),    Size = Vector3.new(5, 5, 5) },
			{ Pos = Vector3.new(-20, 0, 0),   Size = Vector3.new(5, 5, 5) },
			{ Pos = Vector3.new(0, 0, 20),    Size = Vector3.new(5, 5, 5) },
			{ Pos = Vector3.new(0, 0, -20),   Size = Vector3.new(5, 5, 5) },
			{ Pos = Vector3.new(28, 0, 28),   Size = Vector3.new(7, 6, 7) },
			{ Pos = Vector3.new(-28, 0, -28), Size = Vector3.new(7, 6, 7) },
		},
		SpawnPoints = {
			Vector3.new(-35, 4, -35), Vector3.new(35, 4, 35),
			Vector3.new(-35, 4, 35),  Vector3.new(35, 4, -35),
			Vector3.new(0, 4, -38),   Vector3.new(0, 4, 38),
			Vector3.new(-38, 4, 0),   Vector3.new(38, 4, 0),
		},
	},

	-- ===================== MAPA 4 (vila, com tema "Theme = Village") =====================
	-- Campos extras lidos pelo MapGenerator quando Theme == "Village":
	-- Houses, Towers, Trees, TrainingPosts, Monument, Gate, Arena
	{
		Name = "Vila Oculta",
		Theme = "Village",
		Size = Vector3.new(140, 1, 140),
		FloorColor = Color3.fromRGB(195, 165, 110),
		ObstacleColor = Color3.fromRGB(150, 115, 70),
		Material = Enum.Material.Ground,
		Obstacles = {},
		SpawnPoints = {
			Vector3.new(-60, 4, -60), Vector3.new(60, 4, -60),
			Vector3.new(-60, 4, 60),  Vector3.new(60, 4, 60),
			Vector3.new(0, 4, -65),   Vector3.new(0, 4, 65),
			Vector3.new(-65, 4, 0),   Vector3.new(65, 4, 0),
		},
		Houses = {
			{ Pos = Vector3.new(20, 0, 35),  Color = Color3.fromRGB(225, 200, 160) },
			{ Pos = Vector3.new(-22, 0, 33), Color = Color3.fromRGB(210, 190, 150) },
			{ Pos = Vector3.new(34, 0, 8),   Color = Color3.fromRGB(220, 195, 155) },
			{ Pos = Vector3.new(-34, 0, 6),  Color = Color3.fromRGB(215, 188, 148) },
			{ Pos = Vector3.new(30, 0, -18), Color = Color3.fromRGB(225, 200, 160) },
			{ Pos = Vector3.new(-30, 0, -20),Color = Color3.fromRGB(210, 190, 150) },
			{ Pos = Vector3.new(14, 0, 18),  Color = Color3.fromRGB(220, 195, 155) },
			{ Pos = Vector3.new(-16, 0, 16), Color = Color3.fromRGB(215, 188, 148) },
		},
		Towers = {
			{ Pos = Vector3.new(0, 0, 0), Height = 14 },
		},
		TrainingPosts = {
			Vector3.new(42, 0, -40), Vector3.new(46, 0, -37), Vector3.new(50, 0, -41),
			Vector3.new(44, 0, -45), Vector3.new(48, 0, -46),
		},
		Trees = {
			Vector3.new(-44, 0, -40), Vector3.new(-50, 0, -38), Vector3.new(-55, 0, -44),
			Vector3.new(-48, 0, -50), Vector3.new(-42, 0, -52), Vector3.new(-56, 0, -32),
			Vector3.new(-38, 0, -46), Vector3.new(-52, 0, -55), Vector3.new(-60, 0, -46),
			Vector3.new(-46, 0, -58),
		},
		Monument = { Pos = Vector3.new(0, 0, -58) },
		Gate = { Pos = Vector3.new(0, 0, 60) },
		Arena = { Pos = Vector3.new(48, 0, 42), Radius = 13 },
	},
}

return Maps
