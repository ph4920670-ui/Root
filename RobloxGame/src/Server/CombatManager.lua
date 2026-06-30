--[[
	CombatManager (ModuleScript)
	Combate autoritativo. Acerta tanto JOGADORES quanto BOTS (modelos com
	Humanoid dentro da pasta workspace.Enemies). Mostra números de dano.

	Local no Studio: ServerScriptService > Server > CombatManager
]]

local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local Shared = ReplicatedStorage:WaitForChild("Shared")
local Brawlers = require(Shared.Brawlers)
local Net = require(Shared.Net)

local CombatManager = {}

local nextAttack = {}
local nextSpecial = {}
local lastAttacker = {} -- [character/model vítima] = player atacante

local attackEvent = Net.Event("Attack")
local specialEvent = Net.Event("Special")
local fxEvent = Net.Event("AttackFX")
local hitEvent = Net.Event("Hit")

local function getAliveCharacter(player)
	local char = player.Character
	if not char then
		return nil
	end
	local hum = char:FindFirstChildOfClass("Humanoid")
	local root = char:FindFirstChild("HumanoidRootPart")
	if hum and root and hum.Health > 0 then
		return char, hum, root
	end
	return nil
end

-- junta todos os alvos válidos (jogadores + bots), menos o atacante
local function gatherTargets(attackerPlayer, attackerChar)
	local targets = {}
	for _, other in ipairs(Players:GetPlayers()) do
		if other ~= attackerPlayer then
			local c, h, r = getAliveCharacter(other)
			if c then
				table.insert(targets, { char = c, hum = h, root = r })
			end
		end
	end
	local folder = workspace:FindFirstChild("Enemies")
	if folder then
		for _, m in ipairs(folder:GetChildren()) do
			local h = m:FindFirstChildOfClass("Humanoid")
			local r = m:FindFirstChild("HumanoidRootPart")
			if h and r and h.Health > 0 and m ~= attackerChar then
				table.insert(targets, { char = m, hum = h, root = r })
			end
		end
	end
	return targets
end

local function hasLineOfSight(origin, attackerChar, targetChar, targetPos)
	local params = RaycastParams.new()
	params.FilterType = Enum.RaycastFilterType.Exclude
	params.FilterDescendantsInstances = { attackerChar, targetChar }
	local result = workspace:Raycast(origin, (targetPos - origin), params)
	return result == nil
end

local function fireCone(player, direction, damage, range, spreadDeg)
	local attackerChar, _, attackerRoot = getAliveCharacter(player)
	if not attackerChar then
		return
	end

	local origin = attackerRoot.Position
	direction = Vector3.new(direction.X, 0, direction.Z)
	if direction.Magnitude < 0.01 then
		return
	end
	direction = direction.Unit

	local brawlerName = attackerChar:GetAttribute("Brawler")
	local color = Brawlers[brawlerName] and Brawlers[brawlerName].Color or Color3.new(1, 1, 1)
	local spreadRad = math.rad(spreadDeg)

	for _, t in ipairs(gatherTargets(player, attackerChar)) do
		if not t.char:FindFirstChildOfClass("ForceField") then
			local flat = Vector3.new(t.root.Position.X - origin.X, 0, t.root.Position.Z - origin.Z)
			local dist = flat.Magnitude
			if dist <= range and dist > 0.01 then
				local angle = math.acos(math.clamp(direction:Dot(flat.Unit), -1, 1))
				if angle <= spreadRad then
					if hasLineOfSight(origin, attackerChar, t.char, t.root.Position) then
						lastAttacker[t.char] = player
						t.hum:TakeDamage(damage)
						hitEvent:FireAllClients(t.root.Position, damage, color)
					end
				end
			end
		end
	end

	fxEvent:FireAllClients(origin, direction, range, color)
end

function CombatManager.GetLastAttacker(character)
	return lastAttacker[character]
end

function CombatManager.ClearLastAttacker(character)
	lastAttacker[character] = nil
end

function CombatManager.Init()
	attackEvent.OnServerEvent:Connect(function(player, direction)
		if typeof(direction) ~= "Vector3" then
			return
		end
		local char = getAliveCharacter(player)
		if not char then
			return
		end
		local b = Brawlers[char:GetAttribute("Brawler")]
		if not b then
			return
		end
		local now = os.clock()
		if (nextAttack[player] or 0) > now then
			return
		end
		nextAttack[player] = now + b.ReloadTime
		fireCone(player, direction, b.Damage, b.Range, b.Spread)
	end)

	specialEvent.OnServerEvent:Connect(function(player, direction)
		if typeof(direction) ~= "Vector3" then
			return
		end
		local char = getAliveCharacter(player)
		if not char then
			return
		end
		local b = Brawlers[char:GetAttribute("Brawler")]
		if not b or not b.Special then
			return
		end
		local now = os.clock()
		if (nextSpecial[player] or 0) > now then
			return
		end
		nextSpecial[player] = now + b.Special.Cooldown
		fireCone(player, direction, b.Special.Damage, b.Special.Range, b.Special.Spread)
	end)

	Players.PlayerRemoving:Connect(function(player)
		nextAttack[player] = nil
		nextSpecial[player] = nil
		for victim, attacker in pairs(lastAttacker) do
			if attacker == player then
				lastAttacker[victim] = nil
			end
		end
	end)
end

return CombatManager
