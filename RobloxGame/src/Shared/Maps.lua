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

	-- ===================== MAPA 4: VILA NINJA (Theme = "Village") =====================
	-- Layout: portão (sul) -> caminho com cerejeiras/lanternas -> praça da fonte
	-- -> templo (centro) -> rio com ponte -> área de treino / floresta / caverna (norte)
	-- Arena de batalha fica num braço a leste. Casas espalhadas pelo centro.
	{
		Name = "Vila Ninja",
		Theme = "Village",
		Size = Vector3.new(150, 1, 150),
		FloorColor = Color3.fromRGB(125, 160, 85),
		ObstacleColor = Color3.fromRGB(150, 115, 70),
		Material = Enum.Material.Grass,
		Obstacles = {},
		SpawnPoints = {
			Vector3.new(-65, 4, -65), Vector3.new(65, 4, -65),
			Vector3.new(-65, 4, 65),  Vector3.new(65, 4, 65),
			Vector3.new(0, 4, -70),   Vector3.new(0, 4, 70),
			Vector3.new(-70, 4, 0),   Vector3.new(70, 4, 0),
		},

		-- casas de telhado vermelho espalhadas pelo centro da vila
		Houses = {
			{ Pos = Vector3.new(20, 0, 38),   Color = Color3.fromRGB(225, 200, 160) },
			{ Pos = Vector3.new(-22, 0, 36),  Color = Color3.fromRGB(210, 190, 150) },
			{ Pos = Vector3.new(36, 0, 12),   Color = Color3.fromRGB(220, 195, 155) },
			{ Pos = Vector3.new(-36, 0, 10),  Color = Color3.fromRGB(215, 188, 148) },
			{ Pos = Vector3.new(32, 0, -10),  Color = Color3.fromRGB(225, 200, 160) },
			{ Pos = Vector3.new(-32, 0, -10), Color = Color3.fromRGB(210, 190, 150) },
			{ Pos = Vector3.new(16, 0, 18),   Color = Color3.fromRGB(220, 195, 155) },
			{ Pos = Vector3.new(-18, 0, 16),  Color = Color3.fromRGB(215, 188, 148) },
			{ Pos = Vector3.new(8, 0, 50),    Color = Color3.fromRGB(220, 195, 155) },
			{ Pos = Vector3.new(-10, 0, 52),  Color = Color3.fromRGB(215, 188, 148) },
		},

		-- templo antigo (centro da vila)
		Temple = { Pos = Vector3.new(0, 0, 0), Width = 20, Depth = 20, Height = 11 },

		-- praça central com fonte, no caminho entre o portão e o templo
		Fountain = { Pos = Vector3.new(0, 0, 28), Radius = 5 },

		-- rio com ponte separando a vila (sul) da área de treino/floresta (norte)
		River = {
			Pos = Vector3.new(0, -0.3, -36),
			Size = Vector3.new(150, 0.8, 14),
			Bridge = { Pos = Vector3.new(0, 0.3, -36), Size = Vector3.new(7, 0.6, 20) },
		},

		-- área de treinamento (norte, a leste da ponte)
		TrainingPosts = {
			Vector3.new(38, 0, -52), Vector3.new(42, 0, -48), Vector3.new(46, 0, -54),
			Vector3.new(40, 0, -58), Vector3.new(44, 0, -44),
		},

		-- floresta densa (norte, a oeste) + caverna secreta escondida nela
		Trees = {
			Vector3.new(-44, 0, -48), Vector3.new(-50, 0, -44), Vector3.new(-55, 0, -52),
			Vector3.new(-48, 0, -58), Vector3.new(-40, 0, -60), Vector3.new(-58, 0, -38),
			Vector3.new(-36, 0, -52), Vector3.new(-52, 0, -64), Vector3.new(-62, 0, -50),
			Vector3.new(-46, 0, -66), Vector3.new(-30, 0, -58), Vector3.new(-60, 0, -60),
		},
		Cave = { Pos = Vector3.new(-66, 0, -28) },

		-- cerejeiras ao longo do caminho principal e da praça
		CherryTrees = {
			Vector3.new(10, 0, 12),  Vector3.new(-10, 0, 12),
			Vector3.new(14, 0, 28),  Vector3.new(-14, 0, 28),
			Vector3.new(10, 0, 44),  Vector3.new(-10, 0, 44),
			Vector3.new(20, 0, 58),  Vector3.new(-20, 0, 58),
			Vector3.new(0, 0, -2),   Vector3.new(28, 0, 0),
		},

		-- bambuzais perto da floresta e ladeando o templo
		BambooClusters = {
			{ Pos = Vector3.new(-12, 0, -8), Count = 7, Radius = 3 },
			{ Pos = Vector3.new(12, 0, -8),  Count = 7, Radius = 3 },
			{ Pos = Vector3.new(-58, 0, -56),Count = 6, Radius = 2.5 },
		},

		-- monumento de pedra no fundo
		Monument = { Pos = Vector3.new(0, 0, -68) },

		-- portão de entrada (sul)
		Gate = { Pos = Vector3.new(0, 0, 64) },

		-- arena de batalha (braço a leste)
		Arena = { Pos = Vector3.new(56, 0, 40), Radius = 13 },

		-- lanternas japonesas iluminando o caminho principal
		Lanterns = {
			Vector3.new(6, 0, 18),  Vector3.new(-6, 0, 18),
			Vector3.new(6, 0, 36),  Vector3.new(-6, 0, 36),
			Vector3.new(6, 0, 52),  Vector3.new(-6, 0, 52),
			Vector3.new(10, 0, 64), Vector3.new(-10, 0, 64),
		},

		-- cercas de madeira em volta da área de treino e da praça
		Fences = {
			{ From = Vector3.new(28, 0, -40), To = Vector3.new(28, 0, -64) },
			{ From = Vector3.new(28, 0, -64), To = Vector3.new(52, 0, -64) },
			{ From = Vector3.new(-6, 0, 22),  To = Vector3.new(6, 0, 22) },
		},

		-- bancos perto da fonte
		Benches = {
			Vector3.new(0, 0, 20), Vector3.new(0, 0, 36),
		},

		-- bandeiras perto do portão e da arena
		Flags = {
			{ Pos = Vector3.new(-12, 0, 62), Color = Color3.fromRGB(180, 30, 30) },
			{ Pos = Vector3.new(12, 0, 62),  Color = Color3.fromRGB(180, 30, 30) },
			{ Pos = Vector3.new(42, 0, 40),  Color = Color3.fromRGB(40, 60, 150) },
		},

		-- placas indicando os locais
		Signs = {
			{ Pos = Vector3.new(8, 0, 60),    Text = "Entrada da Vila" },
			{ Pos = Vector3.new(4, 0, 22),    Text = "Praça da Fonte" },
			{ Pos = Vector3.new(8, 0, -4),    Text = "Templo Antigo" },
			{ Pos = Vector3.new(34, 0, -38),  Text = "Treinamento" },
			{ Pos = Vector3.new(-34, 0, -38), Text = "Floresta Densa" },
			{ Pos = Vector3.new(48, 0, 28),   Text = "Arena de Batalha" },
		},

		DecorDensity = 55,

		-- ruas de pedra ligando portão -> praça -> templo -> ponte
		Streets = {
			{ From = Vector3.new(0, 0, 64), To = Vector3.new(0, 0, 28), Width = 9 },
			{ From = Vector3.new(0, 0, 28), To = Vector3.new(0, 0, 0),  Width = 9 },
			{ From = Vector3.new(0, 0, 0),  To = Vector3.new(0, 0, -36), Width = 7 },
		},
	},
}

return Maps
