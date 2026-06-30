--[[
	CombatManager (ModuleScript)
	Cuida do combate de forma AUTORITATIVA (o servidor decide o dano, pra
	evitar trapaça). O cliente só pede "atacar nessa direção".

	Como funciona o tiro: a partir do jogador, acerta inimigos que estejam
	dentro do ALCANCE e dentro do ângulo de ABERTURA (cone), desde que não
	tenha obstáculo no meio.

	Local no Studio: ServerScriptService > Server > CombatManager
]]

local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local Shared = ReplicatedStorage:WaitForChild("Shared")
local Brawlers = require(Shared.Brawlers)
local Net = require(Shared.Net)

local CombatManager = {}

local nextAttack = {}   -- [player] = tempo (os) em que pode atacar de novo
local nextSpecial = {}  -- [player] = tempo (os) em que pode usar especial
local lastAttacker = {} -- [player vítima] = player atacante

local attackEvent = Net.Event("Attack")
local specialEvent = Net.Event("Special")
local fxEvent = Net.Event("AttackFX")

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

local function hasLineOfSight(origin, attackerChar, targetChar, targetPos)
	local params = RaycastParams.new()
	params.FilterType = Enum.RaycastFilterType.Exclude
	-- ignora o atacante e o alvo: assim só obstáculos no meio bloqueiam
	params.FilterDescendantsInstances = { attackerChar, targetChar }
	local result = workspace:Raycast(origin, (targetPos - origin), params)
	-- se bateu em algo (um obstáculo) antes do alvo, está bloqueado
	return result == nil
end

-- Aplica um "tiro em cone" e retorna quantos inimigos acertou
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

	local spreadRad = math.rad(spreadDeg)

	for _, other in ipairs(Players:GetPlayers()) do
		if other ~= player then
			local otherChar, otherHum, otherRoot = getAliveCharacter(other)
			if otherChar and not otherChar:FindFirstChildOfClass("ForceField") then
				local toTarget = otherRoot.Position - origin
				local flat = Vector3.new(toTarget.X, 0, toTarget.Z)
				local dist = flat.Magnitude
				if dist <= range and dist > 0.01 then
					local angle = math.acos(math.clamp(direction:Dot(flat.Unit), -1, 1))
					if angle <= spreadRad then
						if hasLineOfSight(origin, attackerChar, otherChar, otherRoot.Position) then
							lastAttacker[other] = player
							otherHum:TakeDamage(damage)
						end
					end
				end
			end
		end
	end

	-- avisa todos os clientes pra desenharem o traçado do tiro
	local brawlerName = attackerChar:GetAttribute("Brawler")
	local color = Brawlers[brawlerName] and Brawlers[brawlerName].Color or Color3.new(1, 1, 1)
	fxEvent:FireAllClients(origin, direction, range, color)
end

function CombatManager.GetLastAttacker(player)
	return lastAttacker[player]
end

function CombatManager.ClearLastAttacker(player)
	lastAttacker[player] = nil
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
		local brawlerName = char:GetAttribute("Brawler")
		local b = Brawlers[brawlerName]
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
		local brawlerName = char:GetAttribute("Brawler")
		local b = Brawlers[brawlerName]
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
		lastAttacker[player] = nil
		-- remove referências como atacante de outros
		for victim, attacker in pairs(lastAttacker) do
			if attacker == player then
				lastAttacker[victim] = nil
			end
		end
	end)
end

return CombatManager
