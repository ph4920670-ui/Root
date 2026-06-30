--[[
	MapGenerator (ModuleScript)
	Constrói o mapa em 3D a partir de Shared/Maps, com acabamento bonito:
	borda neon, paredes de vidro, pads de nascimento iluminados e obstáculos.

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

function MapGenerator.Build(mapDef)
	local model = Instance.new("Model")
	model.Name = "Map_" .. mapDef.Name
	local accent = accentOf(mapDef.FloorColor)

	-- chão (topo em y = 0)
	local floor = makePart("Floor", mapDef.Size, Vector3.new(0, -mapDef.Size.Y / 2, 0),
		mapDef.FloorColor, mapDef.Material, model)
	floor.Reflectance = 0.02

	local halfX = mapDef.Size.X / 2
	local halfZ = mapDef.Size.Z / 2

	-- paredes de vidro escuro
	local function wall(name, size, pos)
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

	-- trilho neon no topo das bordas
	local trimH = 0.6
	local trimY = WALL_HEIGHT + trimH / 2
	local function trim(size, pos)
		local t = makePart("Trim", size, pos, accent, Enum.Material.Neon, model)
		return t
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

	-- ===== DECORAÇÃO =====
	-- postes de luz nos 4 cantos (com luz de verdade)
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

	-- barris (cilindros de madeira) e caixotes (blocos) espalhados pra dar cobertura
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

	-- ===== TEMA DE VILA (mapas com Theme == "Village") =====
	if mapDef.Theme == "Village" then
		-- casas (cubo + telhado)
		for i, h in ipairs(mapDef.Houses or {}) do
			local roofColor = h.RoofColor or Color3.fromRGB(170, 60, 50)
			local base = makePart("House" .. i, Vector3.new(7, 5, 7), h.Pos + Vector3.new(0, 2.5, 0),
				h.Color or Color3.fromRGB(225, 200, 160), Enum.Material.SmoothPlastic, model)
			base.CastShadow = true
			local roof = makePart("HouseRoof" .. i, Vector3.new(8.6, 0.6, 8.6), h.Pos + Vector3.new(0, 5.3, 0),
				roofColor, Enum.Material.SmoothPlastic, model)
			roof.CastShadow = true
			makePart("HouseCap" .. i, Vector3.new(1, 1.6, 1), h.Pos + Vector3.new(0, 6.3, 0),
				roofColor, Enum.Material.SmoothPlastic, model)
		end

		-- torre central
		for i, t in ipairs(mapDef.Towers or {}) do
			local tower = makePart("Tower" .. i, Vector3.new(11, t.Height, 11),
				t.Pos + Vector3.new(0, t.Height / 2, 0), Color3.fromRGB(225, 200, 160), Enum.Material.Concrete, model)
			tower.CastShadow = true
			makePart("TowerRoof" .. i, Vector3.new(13, 1, 13), t.Pos + Vector3.new(0, t.Height + 0.5, 0),
				Color3.fromRGB(170, 60, 50), Enum.Material.SmoothPlastic, model)
		end

		-- bonecos de treino (postes)
		for i, pp in ipairs(mapDef.TrainingPosts or {}) do
			makePart("TrainingPost" .. i, Vector3.new(1, 4, 1), pp + Vector3.new(0, 2, 0),
				Color3.fromRGB(120, 90, 60), Enum.Material.Wood, model)
		end

		-- floresta (árvores)
		for i, tp in ipairs(mapDef.Trees or {}) do
			makePart("TreeTrunk" .. i, Vector3.new(1.4, 5, 1.4), tp + Vector3.new(0, 2.5, 0),
				Color3.fromRGB(90, 60, 40), Enum.Material.Wood, model)
			local leaves = makePart("TreeLeaves" .. i, Vector3.new(6, 6, 6), tp + Vector3.new(0, 7, 0),
				Color3.fromRGB(55, 125, 65), Enum.Material.Grass, model)
			leaves.Shape = Enum.PartType.Ball
			leaves.CastShadow = true
		end

		-- monumento (parede de pedra com emblemas circulares)
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

		-- portão de entrada (arco decorativo)
		if mapDef.Gate then
			local gp = mapDef.Gate.Pos
			makePart("GatePillarL", Vector3.new(2, 12, 2), gp + Vector3.new(-7, 6, 0), Color3.fromRGB(170, 60, 50), Enum.Material.Wood, model)
			makePart("GatePillarR", Vector3.new(2, 12, 2), gp + Vector3.new(7, 6, 0), Color3.fromRGB(170, 60, 50), Enum.Material.Wood, model)
			makePart("GateBeam", Vector3.new(18, 1.4, 2), gp + Vector3.new(0, 12, 0), Color3.fromRGB(170, 60, 50), Enum.Material.Wood, model)
			makePart("GateBeam2", Vector3.new(20, 1, 2.4), gp + Vector3.new(0, 10, 0), Color3.fromRGB(200, 80, 60), Enum.Material.Wood, model)
		end

		-- arena (anel circular de muretas)
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
	end

	model.Parent = workspace
	return model
end

return MapGenerator
