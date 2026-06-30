--[[
	MapGenerator (ModuleScript)
	Constrói um mapa em 3D a partir da definição em Shared/Maps.
	Cria chão, paredes em volta (pra ninguém cair) e os obstáculos.

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

-- Constrói o mapa no workspace e devolve o Model criado
function MapGenerator.Build(mapDef)
	local model = Instance.new("Model")
	model.Name = "Map_" .. mapDef.Name

	-- chão (topo em y = 0)
	makePart("Floor", mapDef.Size, Vector3.new(0, -mapDef.Size.Y / 2, 0),
		mapDef.FloorColor, mapDef.Material, model)

	-- paredes em volta
	local halfX = mapDef.Size.X / 2
	local halfZ = mapDef.Size.Z / 2
	local wallColor = mapDef.ObstacleColor
	local wallMat = Enum.Material.Concrete
	makePart("WallN", Vector3.new(mapDef.Size.X + WALL_THICK * 2, WALL_HEIGHT, WALL_THICK),
		Vector3.new(0, WALL_HEIGHT / 2, halfZ + WALL_THICK / 2), wallColor, wallMat, model)
	makePart("WallS", Vector3.new(mapDef.Size.X + WALL_THICK * 2, WALL_HEIGHT, WALL_THICK),
		Vector3.new(0, WALL_HEIGHT / 2, -halfZ - WALL_THICK / 2), wallColor, wallMat, model)
	makePart("WallE", Vector3.new(WALL_THICK, WALL_HEIGHT, mapDef.Size.Z),
		Vector3.new(halfX + WALL_THICK / 2, WALL_HEIGHT / 2, 0), wallColor, wallMat, model)
	makePart("WallW", Vector3.new(WALL_THICK, WALL_HEIGHT, mapDef.Size.Z),
		Vector3.new(-halfX - WALL_THICK / 2, WALL_HEIGHT / 2, 0), wallColor, wallMat, model)

	-- obstáculos (a base fica no nível do chão)
	for i, o in ipairs(mapDef.Obstacles) do
		makePart("Obstacle" .. i, o.Size,
			o.Pos + Vector3.new(0, o.Size.Y / 2, 0),
			mapDef.ObstacleColor, Enum.Material.Brick, model)
	end

	model.Parent = workspace
	return model
end

return MapGenerator
