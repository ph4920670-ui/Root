--[[
	Net (ModuleScript)
	Pequeno ajudante pra criar/pegar RemoteEvents sem dor de cabeça.
	No servidor ele CRIA o remote; no cliente ele ESPERA o remote existir.
	Assim você não precisa criar os RemoteEvents manualmente no Studio.

	Uso:
	  local Net = require(ReplicatedStorage.Shared.Net)
	  local attack = Net.Event("Attack")

	Local no Studio: ReplicatedStorage > Shared > Net
]]

local RunService = game:GetService("RunService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local Net = {}
local FOLDER_NAME = "Remotes"

local function getFolder()
	local folder = ReplicatedStorage:FindFirstChild(FOLDER_NAME)
	if folder then
		return folder
	end
	if RunService:IsServer() then
		folder = Instance.new("Folder")
		folder.Name = FOLDER_NAME
		folder.Parent = ReplicatedStorage
		return folder
	end
	return ReplicatedStorage:WaitForChild(FOLDER_NAME)
end

function Net.Event(name)
	local folder = getFolder()
	local ev = folder:FindFirstChild(name)
	if ev then
		return ev
	end
	if RunService:IsServer() then
		ev = Instance.new("RemoteEvent")
		ev.Name = name
		ev.Parent = folder
		return ev
	end
	return folder:WaitForChild(name)
end

return Net
