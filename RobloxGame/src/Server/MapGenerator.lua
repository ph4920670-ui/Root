--[[
	MapGenerator (ModuleScript)
	Constrói o mapa em 3D a partir de Shared/Maps, com acabamento bonito:
	borda, paredes, pads de nascimento iluminados, obstáculos e (para mapas
	com Theme == "Village") um conjunto temático de vila ninja: casas com
	telhado de duas águas, cerejeiras, bambu, rio com ponte, fonte, templo,
	caverna secreta, lanternas, cercas, bancos, bandeiras e placas com texto.

	Tudo é construído só com peças do Roblox (sem upload de modelos/texturas).

	Local no Studio: ServerScriptService > Server > MapGenerator
]]

local MapGenerator = {}

local WALL_HEIGHT = 18
local WALL_THICK = 4

local function makePart(name, size, position, color, material, parent)
	local p = Instance.new("Part")
	p.Name = name
	p.Anchored = true
	p.Size = size
	p.Position = position
	p.Color = color
	p.Material = material
	p.TopSurface = Enum.SurfaceType.Smooth
	p.BottomSurface = Enum.SurfaceType.Smooth
	p.Parent = parent
	return p
end

-- clareia uma cor pra usar como "neon de destaque"
local function accentOf(color)
	return Color3.new(
		math.min(1, color.R * 0.5 + 0.5),
		math.min(1, color.G * 0.5 + 0.55),
		math.min(1, color.B * 0.5 + 0.6)
	)
end

-- painel inclinado entre dois pontos (usado pros telhados); matematicamente
-- robusto porque usa CFrame.lookAt em vez de adivinhar a orientação de WedgePart
local function slopedPanel(name, from, to, widthAxisLen, thickness, color, material, parent)
	local mid = (from + to) / 2
	local len = (to - from).Magnitude
	local panel = Instance.new("Part")
	panel.Name = name
	panel.Anchored = true
	panel.CanCollide = true
	panel.CastShadow = true
	panel.Material = material
	panel.Color = color
	panel.Size = Vector3.new(widthAxisLen, thickness, len)
	panel.CFrame = CFrame.lookAt(mid, to)
	panel.Parent = parent
	return panel
end

-- ===================================================================
-- CONSTRUTORES TEMÁTICOS (vila ninja)
-- ===================================================================

local function buildHouse(model, h)
	local pos = h.Pos
	local w, d, height = h.Width or 8, h.Depth or 8, h.Height or 5
	local wallColor = h.Color or Color3.fromRGB(225, 200, 160)
	local roofColor = h.RoofColor or Color3.fromRGB(180, 55, 45)
	local trimColor = h.TrimColor or Color3.fromRGB(95, 65, 40)

	local base = makePart("HouseBase", Vector3.new(w + 1, 0.6, d + 1), pos + Vector3.new(0, 0.3, 0),
		Color3.fromRGB(150, 145, 140), Enum.Material.Slate, model)
	base.CastShadow = true

	local body = makePart("HouseBody", Vector3.new(w, height, d), pos + Vector3.new(0, 0.6 + height / 2, 0),
		wallColor, Enum.Material.SmoothPlastic, model)
	body.CastShadow = true

	-- janelas (painéis claros nas laterais)
	makePart("HouseWindowL", Vector3.new(0.12, height * 0.4, d * 0.5),
		pos + Vector3.new(w / 2 + 0.03, 0.6 + height * 0.55, 0), Color3.fromRGB(255, 248, 220), Enum.Material.Glass, model)
	makePart("HouseWindowR", Vector3.new(0.12, height * 0.4, d * 0.5),
		pos + Vector3.new(-w / 2 - 0.03, 0.6 + height * 0.55, 0), Color3.fromRGB(255, 248, 220), Enum.Material.Glass, model)

	-- pilares de canto
	for _, off in ipairs({
		Vector3.new(w / 2 - 0.25, 0, d / 2 - 0.25), Vector3.new(-(w / 2 - 0.25), 0, d / 2 - 0.25),
		Vector3.new(w / 2 - 0.25, 0, -(d / 2 - 0.25)), Vector3.new(-(w / 2 - 0.25), 0, -(d / 2 - 0.25)),
	}) do
		makePart("HousePillar", Vector3.new(0.5, height + 0.5, 0.5), pos + off + Vector3.new(0, 0.3 + (height + 0.5) / 2, 0),
			trimColor, Enum.Material.Wood, model)
	end

	-- telhado de duas águas
	local eaveY = 0.6 + height
	local ridgeRise = 2.6
	local halfRun = w / 2 + 0.9
	local ridgeRun = d + 1.6
	local ridgePoint = pos + Vector3.new(0, eaveY + ridgeRise, 0)
	for _, sx in ipairs({ 1, -1 }) do
		local eavePoint = pos + Vector3.new(sx * halfRun, eaveY, 0)
		slopedPanel("RoofPanel", eavePoint, ridgePoint, ridgeRun, 0.4, roofColor, Enum.Material.SmoothPlastic, model)
	end
	makePart("RoofRidge", Vector3.new(0.5, 0.5, ridgeRun), ridgePoint, trimColor, Enum.Material.Wood, model)

	-- varanda (engawa)
	makePart("Porch", Vector3.new(w + 1.2, 0.25, 2), pos + Vector3.new(0, 0.7, d / 2 + 1.4),
		Color3.fromRGB(150, 110, 70), Enum.Material.WoodPlanks, model)
end

local function buildTemple(model, t)
	local pos = t.Pos
	local w, d, height = t.Width or 20, t.Depth or 20, t.Height or 11
	local roofColor = t.RoofColor or Color3.fromRGB(180, 55, 45)
	local wallColor = t.Color or Color3.fromRGB(210, 70, 60)

	local platform = makePart("TemplePlatform", Vector3.new(w + 5, 1.4, d + 5), pos + Vector3.new(0, 0.7, 0),
		Color3.fromRGB(150, 145, 140), Enum.Material.Marble, model)
	platform.CastShadow = true

	local body = makePart("TempleBody", Vector3.new(w, height, d), pos + Vector3.new(0, 1.4 + height / 2, 0),
		wallColor, Enum.Material.SmoothPlastic, model)
	body.CastShadow = true

	for i = 0, 5 do
		local x = -w / 2 + 1.4 + i * (w - 2.8) / 5
		local pillar = makePart("TemplePillar" .. i, Vector3.new(1.2, height, 1.2),
			pos + Vector3.new(x, 1.4 + height / 2, d / 2 - 1.2), Color3.fromRGB(225, 200, 160), Enum.Material.SmoothPlastic, model)
		pillar.CastShadow = true
	end

	-- telhado grande (duas águas)
	local eaveY = 1.4 + height
	local ridgeRise = height * 0.6
	local halfRun = w / 2 + 1.6
	local ridgeRun = d + 3
	local ridgePoint = pos + Vector3.new(0, eaveY + ridgeRise, 0)
	for _, sx in ipairs({ 1, -1 }) do
		local eavePoint = pos + Vector3.new(sx * halfRun, eaveY, 0)
		slopedPanel("TempleRoof", eavePoint, ridgePoint, ridgeRun, 0.5, roofColor, Enum.Material.SmoothPlastic, model)
	end
	makePart("TempleRidge", Vector3.new(0.6, 0.6, ridgeRun), ridgePoint, Color3.fromRGB(90, 60, 40), Enum.Material.Wood, model)

	-- escadaria de entrada
	for i = 1, 6 do
		makePart("TempleStep" .. i, Vector3.new(w * 0.35, 0.3, 1.1), pos + Vector3.new(0, 0.15 + (i - 1) * 0.3, d / 2 + 2 + i * 1.0),
			Color3.fromRGB(150, 145, 140), Enum.Material.Marble, model)
	end
end

local function buildCave(model, c)
	local pos = c.Pos
	local boulders = {
		{ off = Vector3.new(0, 3, -6),  size = Vector3.new(15, 8, 8) },
		{ off = Vector3.new(-7, 3, 2),  size = Vector3.new(9, 7, 11) },
		{ off = Vector3.new(7, 3, 2),   size = Vector3.new(9, 7, 11) },
		{ off = Vector3.new(0, 7.5, 0), size = Vector3.new(17, 6, 15) },
	}
	for i, b in ipairs(boulders) do
		local rock = makePart("CaveRock" .. i, b.size, pos + b.off, Color3.fromRGB(110, 108, 105), Enum.Material.Rock, model)
		rock.CastShadow = true
	end
	local floor = makePart("CaveFloor", Vector3.new(11, 0.5, 11), pos + Vector3.new(0, 0.25, 0),
		Color3.fromRGB(70, 68, 65), Enum.Material.Slate, model)
	local light = Instance.new("PointLight")
	light.Color = Color3.fromRGB(255, 170, 90)
	light.Brightness = 1.6
	light.Range = 18
	light.Parent = floor
	makePart("CaveChest", Vector3.new(2, 1.4, 1.4), pos + Vector3.new(0, 0.95, 0),
		Color3.fromRGB(120, 85, 40), Enum.Material.Wood, model)
end

local function buildFountain(model, f)
	local pos, radius = f.Pos, f.Radius or 5
	local basin = makePart("FountainBasin", Vector3.new(radius * 2, 1.2, radius * 2), pos + Vector3.new(0, 0.6, 0),
		Color3.fromRGB(175, 170, 165), Enum.Material.Marble, model)
	basin.Shape = Enum.PartType.Cylinder
	basin.CFrame = CFrame.new(pos + Vector3.new(0, 0.6, 0)) * CFrame.Angles(0, 0, math.rad(90))

	local water = makePart("FountainWater", Vector3.new(radius * 1.7, 0.6, radius * 1.7), pos + Vector3.new(0, 1.25, 0),
		Color3.fromRGB(80, 165, 215), Enum.Material.Water, model)
	water.Shape = Enum.PartType.Cylinder
	water.CFrame = CFrame.new(pos + Vector3.new(0, 1.25, 0)) * CFrame.Angles(0, 0, math.rad(90))
	water.CanCollide = false

	makePart("FountainColumn", Vector3.new(1.4, 3, 1.4), pos + Vector3.new(0, 1.2 + 1.5, 0),
		Color3.fromRGB(175, 170, 165), Enum.Material.Marble, model)
	local top = makePart("FountainTop", Vector3.new(2.2, 2.2, 2.2), pos + Vector3.new(0, 1.2 + 3.3, 0),
		Color3.fromRGB(175, 170, 165), Enum.Material.Marble, model)
	top.Shape = Enum.PartType.Ball
end

local function buildRiver(model, r)
	local riverPart = makePart("River", r.Size, r.Pos, Color3.fromRGB(60, 130, 180), Enum.Material.Water, model)
	riverPart.CanCollide = false
	riverPart.Transparency = 0.1

	if r.Bridge then
		local b = r.Bridge
		makePart("BridgeDeck", b.Size, b.Pos, Color3.fromRGB(150, 110, 70), Enum.Material.WoodPlanks, model).CastShadow = true
		local railSize = Vector3.new(0.3, 1.2, b.Size.Z)
		makePart("BridgeRailA", railSize, b.Pos + Vector3.new(b.Size.X / 2 - 0.15, 0.9, 0), Color3.fromRGB(110, 80, 50), Enum.Material.Wood, model)
		makePart("BridgeRailB", railSize, b.Pos + Vector3.new(-b.Size.X / 2 + 0.15, 0.9, 0), Color3.fromRGB(110, 80, 50), Enum.Material.Wood, model)
	end
end

local function buildLantern(model, pos, i)
	makePart("LanternBase" .. i, Vector3.new(1.6, 1.4, 1.6), pos + Vector3.new(0, 0.7, 0), Color3.fromRGB(120, 118, 115), Enum.Material.Slate, model)
	makePart("LanternPole" .. i, Vector3.new(0.8, 2.2, 0.8), pos + Vector3.new(0, 2.4, 0), Color3.fromRGB(120, 118, 115), Enum.Material.Slate, model)
	local box = makePart("LanternBox" .. i, Vector3.new(1.8, 1.6, 1.8), pos + Vector3.new(0, 4.3, 0), Color3.fromRGB(255, 225, 150), Enum.Material.Neon, model)
	local light = Instance.new("PointLight")
	light.Color = Color3.fromRGB(255, 190, 110)
	light.Brightness = 2.5
	light.Range = 20
	light.Parent = box
	makePart("LanternCap" .. i, Vector3.new(2.4, 0.6, 2.4), pos + Vector3.new(0, 5.3, 0), Color3.fromRGB(90, 40, 35), Enum.Material.SmoothPlastic, model)
end

local function buildFence(model, fence, i)
	local from, to = fence.From, fence.To
	local len = (to - from).Magnitude
	local segs = math.max(1, math.floor(len / 4))
	for s = 0, segs do
		local p = from:Lerp(to, s / segs)
		makePart("FencePost" .. i .. "_" .. s, Vector3.new(0.4, 2.2, 0.4), p + Vector3.new(0, 1.1, 0), Color3.fromRGB(110, 80, 50), Enum.Material.Wood, model)
	end
	local mid = (from + to) / 2
	local rail = Instance.new("Part")
	rail.Name = "FenceRail" .. i
	rail.Anchored = true
	rail.CanCollide = false
	rail.Material = Enum.Material.Wood
	rail.Color = Color3.fromRGB(110, 80, 50)
	rail.Size = Vector3.new(0.3, 0.3, len)
	rail.CFrame = CFrame.lookAt(mid, to) * CFrame.new(0, 0.9, 0)
	rail.Parent = model
end

local function buildBench(model, pos, i)
	makePart("BenchSeat" .. i, Vector3.new(4, 0.4, 1.4), pos + Vector3.new(0, 1.1, 0), Color3.fromRGB(140, 100, 65), Enum.Material.WoodPlanks, model)
	makePart("BenchBack" .. i, Vector3.new(4, 1.2, 0.3), pos + Vector3.new(0, 1.9, -0.6), Color3.fromRGB(140, 100, 65), Enum.Material.WoodPlanks, model)
	for _, lx in ipairs({ -1.6, 1.6 }) do
		makePart("BenchLeg" .. i, Vector3.new(0.3, 1.1, 1.2), pos + Vector3.new(lx, 0.55, 0), Color3.fromRGB(90, 65, 40), Enum.Material.Wood, model)
	end
end

local function buildFlag(model, pos, color, i)
	makePart("FlagPole" .. i, Vector3.new(0.35, 7, 0.35), pos + Vector3.new(0, 3.5, 0), Color3.fromRGB(90, 85, 80), Enum.Material.Metal, model)
	local cloth = makePart("FlagCloth" .. i, Vector3.new(2.4, 3.2, 0.15), pos + Vector3.new(1.3, 5.6, 0), color or Color3.fromRGB(180, 30, 30), Enum.Material.Fabric, model)
	cloth.CanCollide = false
end

local function buildSign(model, sg, i)
	makePart("SignPost" .. i, Vector3.new(0.4, 3, 0.4), sg.Pos + Vector3.new(0, 1.5, 0), Color3.fromRGB(110, 80, 50), Enum.Material.Wood, model)
	local board = makePart("SignBoard" .. i, Vector3.new(3.4, 1.4, 0.25), sg.Pos + Vector3.new(0, 3.4, 0), Color3.fromRGB(225, 205, 165), Enum.Material.WoodPlanks, model)
	local sgui = Instance.new("SurfaceGui")
	sgui.Face = Enum.NormalId.Front
	sgui.LightInfluence = 0
	sgui.Parent = board
	local label = Instance.new("TextLabel")
	label.Size = UDim2.new(1, 0, 1, 0)
	label.BackgroundTransparency = 1
	label.Font = Enum.Font.GothamBold
	label.TextScaled = true
	label.TextColor3 = Color3.fromRGB(40, 30, 20)
	label.Text = sg.Text or "?"
	label.Parent = sgui
end

local function buildBambooCluster(model, cluster, ci)
	local count = cluster.Count or 6
	local radius = cluster.Radius or 2.5
	for i = 1, count do
		local ang = (i / count) * math.pi * 2
		local r = (i % 3) * (radius / 3) + 0.3
		local off = Vector3.new(math.cos(ang) * r, 0, math.sin(ang) * r)
		local h = 6 + (i % 4)
		makePart("Bamboo" .. ci .. "_" .. i, Vector3.new(0.5, h, 0.5), cluster.Pos + off + Vector3.new(0, h / 2, 0),
			Color3.fromRGB(120, 180, 90), Enum.Material.Grass, model)
	end
end

local function buildMountainBackdrop(model, mapDef)
	local halfX, halfZ = mapDef.Size.X / 2, mapDef.Size.Z / 2
	local spots = {
		{ pos = Vector3.new(0, 0, halfZ + 60),    w = 90, h = 55 },
		{ pos = Vector3.new(halfX + 55, 0, 10),   w = 70, h = 45 },
		{ pos = Vector3.new(-halfX - 55, 0, -10), w = 70, h = 48 },
		{ pos = Vector3.new(20, 0, -halfZ - 60),  w = 85, h = 50 },
	}
	for i, s in ipairs(spots) do
		local mtn = makePart("Mountain" .. i, Vector3.new(s.w, s.h, s.w), s.pos + Vector3.new(0, s.h / 2 - 4, 0),
			Color3.fromRGB(100, 110, 120), Enum.Material.Rock, model)
		mtn.Shape = Enum.PartType.Ball
		mtn.CanCollide = false
		mtn.CanQuery = false
		mtn.CastShadow = true
		local cap = makePart("MountainCap" .. i, Vector3.new(s.w * 0.5, s.h * 0.35, s.w * 0.5), s.pos + Vector3.new(0, s.h * 0.78, 0),
			Color3.fromRGB(235, 235, 240), Enum.Material.Snow, model)
		cap.Shape = Enum.PartType.Ball
		cap.CanCollide = false
		cap.CanQuery = false
	end
end

-- arbustos, pedrinhas e flores espalhados pra não deixar canto vazio
local function scatterDecor(model, mapDef)
	local rng = Random.new(20240501)
	local halfX = mapDef.Size.X / 2 - 6
	local halfZ = mapDef.Size.Z / 2 - 6
	local count = mapDef.DecorDensity or 55
	for i = 1, count do
		local x = rng:NextNumber(-halfX, halfX)
		local z = rng:NextNumber(-halfZ, halfZ)
		local kind = rng:NextInteger(1, 3)
		if kind == 1 then
			local bush = makePart("Bush" .. i, Vector3.new(1.8, 1.4, 1.8), Vector3.new(x, 0.7, z), Color3.fromRGB(60, 130, 70), Enum.Material.Grass, model)
			bush.Shape = Enum.PartType.Ball
			bush.CanCollide = false
		elseif kind == 2 then
			local rock = makePart("Rock" .. i, Vector3.new(1.2 + rng:NextNumber(0, 1), 0.9, 1.1), Vector3.new(x, 0.5, z), Color3.fromRGB(130, 128, 124), Enum.Material.Rock, model)
			rock.CanCollide = false
		else
			local flower = makePart("Flower" .. i, Vector3.new(0.4, 0.4, 0.4), Vector3.new(x, 0.3, z),
				Color3.fromRGB(rng:NextInteger(200, 255), rng:NextInteger(60, 160), rng:NextInteger(120, 200)), Enum.Material.Neon, model)
			flower.Shape = Enum.PartType.Ball
			flower.CanCollide = false
		end
	end
end

-- ===================================================================
-- BUILD principal
-- ===================================================================

function MapGenerator.Build(mapDef)
	local model = Instance.new("Model")
	model.Name = "Map_" .. mapDef.Name
	local accent = accentOf(mapDef.FloorColor)
	local isVillage = mapDef.Theme == "Village"

	-- chão (topo em y = 0)
	local floor = makePart("Floor", mapDef.Size, Vector3.new(0, -mapDef.Size.Y / 2, 0),
		mapDef.FloorColor, mapDef.Material, model)
	floor.Reflectance = 0.02

	local halfX = mapDef.Size.X / 2
	local halfZ = mapDef.Size.Z / 2

	-- paredes: vidro futurista nos mapas normais, muro de pedra na vila
	local function wall(name, size, pos)
		if isVillage then
			local w = makePart(name, size, pos, Color3.fromRGB(150, 140, 120), Enum.Material.Rock, model)
			w.CastShadow = true
			return w
		end
		local w = makePart(name, size, pos, Color3.fromRGB(40, 44, 56), Enum.Material.Glass, model)
		w.Transparency = 0.35
		w.Reflectance = 0.15
		return w
	end
	wall("WallN", Vector3.new(mapDef.Size.X + WALL_THICK * 2, WALL_HEIGHT, WALL_THICK),
		Vector3.new(0, WALL_HEIGHT / 2, halfZ + WALL_THICK / 2))
	wall("WallS", Vector3.new(mapDef.Size.X + WALL_THICK * 2, WALL_HEIGHT, WALL_THICK),
		Vector3.new(0, WALL_HEIGHT / 2, -halfZ - WALL_THICK / 2))
	wall("WallE", Vector3.new(WALL_THICK, WALL_HEIGHT, mapDef.Size.Z),
		Vector3.new(halfX + WALL_THICK / 2, WALL_HEIGHT / 2, 0))
	wall("WallW", Vector3.new(WALL_THICK, WALL_HEIGHT, mapDef.Size.Z),
		Vector3.new(-halfX - WALL_THICK / 2, WALL_HEIGHT / 2, 0))

	-- trilho no topo das bordas
	local trimH = 0.6
	local trimY = WALL_HEIGHT + trimH / 2
	local function trim(size, pos)
		return makePart("Trim", size, pos, accent, Enum.Material.Neon, model)
	end
	trim(Vector3.new(mapDef.Size.X + WALL_THICK * 2, trimH, WALL_THICK), Vector3.new(0, trimY, halfZ + WALL_THICK / 2))
	trim(Vector3.new(mapDef.Size.X + WALL_THICK * 2, trimH, WALL_THICK), Vector3.new(0, trimY, -halfZ - WALL_THICK / 2))
	trim(Vector3.new(WALL_THICK, trimH, mapDef.Size.Z), Vector3.new(halfX + WALL_THICK / 2, trimY, 0))
	trim(Vector3.new(WALL_THICK, trimH, mapDef.Size.Z), Vector3.new(-halfX - WALL_THICK / 2, trimY, 0))

	-- obstáculos (base no chão), com aresta neon em cima
	for i, o in ipairs(mapDef.Obstacles) do
		local block = makePart("Obstacle" .. i, o.Size,
			o.Pos + Vector3.new(0, o.Size.Y / 2, 0),
			mapDef.ObstacleColor, Enum.Material.Concrete, model)
		block.Reflectance = 0.03
		makePart("ObstacleTop" .. i, Vector3.new(o.Size.X, 0.4, o.Size.Z),
			o.Pos + Vector3.new(0, o.Size.Y + 0.2, 0),
			accent, Enum.Material.Neon, model)
	end

	-- pads de nascimento iluminados
	for i, sp in ipairs(mapDef.SpawnPoints) do
		local pad = makePart("SpawnPad" .. i, Vector3.new(0.4, 6, 6),
			Vector3.new(sp.X, 0.25, sp.Z), accent, Enum.Material.Neon, model)
		pad.Shape = Enum.PartType.Cylinder
		pad.CFrame = CFrame.new(sp.X, 0.25, sp.Z) * CFrame.Angles(0, 0, math.rad(90))
		pad.Transparency = 0.25
	end

	-- postes de luz nos 4 cantos (a vila usa lanternas próprias em vez disso)
	if not isVillage then
		local cx, cz = halfX - 8, halfZ - 8
		for _, corner in ipairs({
			Vector3.new(cx, 0, cz), Vector3.new(-cx, 0, cz),
			Vector3.new(cx, 0, -cz), Vector3.new(-cx, 0, -cz),
		}) do
			local pole = makePart("LampPole", Vector3.new(0.6, 11, 0.6),
				corner + Vector3.new(0, 5.5, 0), Color3.fromRGB(40, 40, 48), Enum.Material.Metal, model)
			local bulb = makePart("LampBulb", Vector3.new(1.6, 1.6, 1.6),
				corner + Vector3.new(0, 11, 0), accent, Enum.Material.Neon, model)
			bulb.Shape = Enum.PartType.Ball
			local light = Instance.new("PointLight")
			light.Color = accent
			light.Brightness = 3
			light.Range = 26
			light.Parent = bulb
			pole.CastShadow = true
		end

		-- barris e caixotes (a vila já tem suas próprias estruturas no centro)
		local props = {
			{ kind = "barrel", pos = Vector3.new(15, 0, 0) },
			{ kind = "barrel", pos = Vector3.new(-15, 0, 0) },
			{ kind = "crate",  pos = Vector3.new(0, 0, 15) },
			{ kind = "crate",  pos = Vector3.new(0, 0, -15) },
			{ kind = "crate",  pos = Vector3.new(18, 0, 18) },
			{ kind = "barrel", pos = Vector3.new(-18, 0, -18) },
		}
		for i, p in ipairs(props) do
			if p.kind == "barrel" then
				local b = makePart("Barrel" .. i, Vector3.new(3, 3.4, 3),
					p.pos + Vector3.new(0, 1.7, 0), Color3.fromRGB(120, 80, 45), Enum.Material.WoodPlanks, model)
				b.Shape = Enum.PartType.Cylinder
				b.CFrame = CFrame.new(p.pos + Vector3.new(0, 1.7, 0)) * CFrame.Angles(0, 0, math.rad(90))
				b.CastShadow = true
			else
				local c = makePart("Crate" .. i, Vector3.new(3.2, 3.2, 3.2),
					p.pos + Vector3.new(0, 1.6, 0), Color3.fromRGB(150, 110, 65), Enum.Material.WoodPlanks, model)
				c.CastShadow = true
			end
		end
	end

	-- ===== TEMA DE VILA (mapas com Theme == "Village") =====
	if isVillage then
		for i, h in ipairs(mapDef.Houses or {}) do
			buildHouse(model, h)
		end

		if mapDef.Temple then
			buildTemple(model, mapDef.Temple)
		end

		for i, t in ipairs(mapDef.Towers or {}) do
			local tower = makePart("Tower" .. i, Vector3.new(11, t.Height, 11),
				t.Pos + Vector3.new(0, t.Height / 2, 0), Color3.fromRGB(225, 200, 160), Enum.Material.Concrete, model)
			tower.CastShadow = true
			makePart("TowerRoof" .. i, Vector3.new(13, 1, 13), t.Pos + Vector3.new(0, t.Height + 0.5, 0),
				Color3.fromRGB(170, 60, 50), Enum.Material.SmoothPlastic, model)
		end

		for i, pp in ipairs(mapDef.TrainingPosts or {}) do
			makePart("TrainingPost" .. i, Vector3.new(1, 4, 1), pp + Vector3.new(0, 2, 0),
				Color3.fromRGB(120, 90, 60), Enum.Material.Wood, model)
		end

		for i, tp in ipairs(mapDef.Trees or {}) do
			makePart("TreeTrunk" .. i, Vector3.new(1.4, 5, 1.4), tp + Vector3.new(0, 2.5, 0),
				Color3.fromRGB(90, 60, 40), Enum.Material.Wood, model)
			local leaves = makePart("TreeLeaves" .. i, Vector3.new(6, 6, 6), tp + Vector3.new(0, 7, 0),
				Color3.fromRGB(55, 125, 65), Enum.Material.Grass, model)
			leaves.Shape = Enum.PartType.Ball
			leaves.CastShadow = true
		end

		for i, tp in ipairs(mapDef.CherryTrees or {}) do
			makePart("CherryTrunk" .. i, Vector3.new(1.3, 4.5, 1.3), tp + Vector3.new(0, 2.25, 0),
				Color3.fromRGB(90, 60, 40), Enum.Material.Wood, model)
			local leaves = makePart("CherryLeaves" .. i, Vector3.new(5.5, 5, 5.5), tp + Vector3.new(0, 6.2, 0),
				Color3.fromRGB(255, 180, 210), Enum.Material.Grass, model)
			leaves.Shape = Enum.PartType.Ball
			leaves.CastShadow = true
		end

		for i, cluster in ipairs(mapDef.BambooClusters or {}) do
			buildBambooCluster(model, cluster, i)
		end

		if mapDef.River then
			buildRiver(model, mapDef.River)
		end

		if mapDef.Fountain then
			buildFountain(model, mapDef.Fountain)
		end

		if mapDef.Cave then
			buildCave(model, mapDef.Cave)
		end

		if mapDef.Monument then
			local mPos = mapDef.Monument.Pos
			makePart("MonumentWall", Vector3.new(40, 16, 3), mPos + Vector3.new(0, 8, 0),
				Color3.fromRGB(150, 145, 140), Enum.Material.Rock, model)
			for i = 1, 4 do
				local ex = (i - 2.5) * 9
				local emblem = makePart("MonumentEmblem" .. i, Vector3.new(5, 5, 0.6),
					mPos + Vector3.new(ex, 9, -1.8), accent, Enum.Material.Neon, model)
				emblem.Shape = Enum.PartType.Cylinder
				emblem.CFrame = CFrame.new(mPos + Vector3.new(ex, 9, -1.8)) * CFrame.Angles(0, 0, math.rad(90))
			end
		end

		if mapDef.Gate then
			local gp = mapDef.Gate.Pos
			makePart("GatePillarL", Vector3.new(2, 12, 2), gp + Vector3.new(-7, 6, 0), Color3.fromRGB(170, 60, 50), Enum.Material.Wood, model)
			makePart("GatePillarR", Vector3.new(2, 12, 2), gp + Vector3.new(7, 6, 0), Color3.fromRGB(170, 60, 50), Enum.Material.Wood, model)
			makePart("GateBeam", Vector3.new(18, 1.4, 2), gp + Vector3.new(0, 12, 0), Color3.fromRGB(170, 60, 50), Enum.Material.Wood, model)
			makePart("GateBeam2", Vector3.new(20, 1, 2.4), gp + Vector3.new(0, 10, 0), Color3.fromRGB(200, 80, 60), Enum.Material.Wood, model)
		end

		if mapDef.Arena then
			local ap = mapDef.Arena.Pos
			local radius = mapDef.Arena.Radius or 14
			local segs = 16
			for i = 1, segs do
				local angle = (i - 1) * (2 * math.pi / segs)
				local pos = ap + Vector3.new(math.cos(angle) * radius, 0, math.sin(angle) * radius)
				local seg = makePart("ArenaWall" .. i, Vector3.new(3.2, 3, 1), pos + Vector3.new(0, 1.5, 0),
					Color3.fromRGB(190, 170, 130), Enum.Material.Sandstone, model)
				seg.CFrame = CFrame.new(pos + Vector3.new(0, 1.5, 0)) * CFrame.Angles(0, -angle, 0)
				seg.CastShadow = true
			end
		end

		for i, pos in ipairs(mapDef.Lanterns or {}) do
			buildLantern(model, pos, i)
		end

		for i, fence in ipairs(mapDef.Fences or {}) do
			buildFence(model, fence, i)
		end

		for i, pos in ipairs(mapDef.Benches or {}) do
			buildBench(model, pos, i)
		end

		for i, fl in ipairs(mapDef.Flags or {}) do
			buildFlag(model, fl.Pos, fl.Color, i)
		end

		for i, sg in ipairs(mapDef.Signs or {}) do
			buildSign(model, sg, i)
		end

		buildMountainBackdrop(model, mapDef)
		scatterDecor(model, mapDef)
	end

	model.Parent = workspace
	return model
end

return MapGenerator
