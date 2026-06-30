--[[
	Client (LocalScript)
	Interface, controles, câmera estilo Brawl Stars (vista de cima) e efeitos.

	Local no Studio: StarterPlayer > StarterPlayerScripts > Client (ou Cliente)
]]

local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local UserInputService = game:GetService("UserInputService")
local RunService = game:GetService("RunService")
local Debris = game:GetService("Debris")

local player = Players.LocalPlayer
local mouse = player:GetMouse()
local camera = workspace.CurrentCamera

local Shared = ReplicatedStorage:WaitForChild("Shared")
local Brawlers = require(Shared.Brawlers)
local Net = require(Shared.Net)

local attackEvent = Net.Event("Attack")
local specialEvent = Net.Event("Special")
local buyEvent = Net.Event("BuyBrawler")
local selectEvent = Net.Event("SelectBrawler")
local syncEvent = Net.Event("Sync")
local matchEvent = Net.Event("Match")
local notifyEvent = Net.Event("Notify")
local fxEvent = Net.Event("AttackFX")
local hitEvent = Net.Event("Hit")

local myData = { Coins = 0, Owned = {}, Selected = "Shelly" }
local superCooldownUntil = 0
local superCooldownTotal = 1

-- ===================================================================
-- HELPERS DE UI
-- ===================================================================
local function corner(parent, radius)
	local c = Instance.new("UICorner")
	c.CornerRadius = UDim.new(0, radius or 8)
	c.Parent = parent
	return c
end

local function gradient(parent, c1, c2, rot)
	local g = Instance.new("UIGradient")
	g.Color = ColorSequence.new(c1, c2)
	g.Rotation = rot or 90
	g.Parent = parent
	return g
end

local function stroke(parent, color, thickness, transparency)
	local s = Instance.new("UIStroke")
	s.Color = color or Color3.fromRGB(0, 0, 0)
	s.Thickness = thickness or 1.5
	s.Transparency = transparency or 0.4
	s.Parent = parent
	return s
end

local function make(class, props, parent)
	local obj = Instance.new(class)
	for k, v in pairs(props) do
		obj[k] = v
	end
	if parent then
		obj.Parent = parent
	end
	return obj
end

-- ===================================================================
-- CÂMERA estilo Brawl Stars (vista de cima, inclinada)
-- ===================================================================
local CAM_HEIGHT = 50
local CAM_BACK = 32
RunService:BindToRenderStep("BrawlCam", Enum.RenderPriority.Camera.Value + 1, function()
	local char = player.Character
	local root = char and char:FindFirstChild("HumanoidRootPart")
	if not root then
		return
	end
	camera.CameraType = Enum.CameraType.Scriptable
	local target = root.Position
	local desired = CFrame.lookAt(target + Vector3.new(0, CAM_HEIGHT, CAM_BACK), target)
	local alpha = (camera.CFrame.Position - desired.Position).Magnitude > 120 and 1 or 0.16
	camera.CFrame = camera.CFrame:Lerp(desired, alpha)
end)

-- ===================================================================
-- INTERFACE
-- ===================================================================
local gui = make("ScreenGui", {
	Name = "HUD",
	ResetOnSpawn = false,
	IgnoreGuiInset = true,
	ZIndexBehavior = Enum.ZIndexBehavior.Sibling,
}, player:WaitForChild("PlayerGui"))

-- Barra superior
local topBar = make("Frame", {
	Size = UDim2.new(1, 0, 0, 54),
	BackgroundColor3 = Color3.fromRGB(28, 30, 42),
	BorderSizePixel = 0,
}, gui)
gradient(topBar, Color3.fromRGB(38, 41, 58), Color3.fromRGB(20, 22, 32))

-- pílula de moedas
local coinPill = make("Frame", {
	Size = UDim2.new(0, 150, 0, 36),
	Position = UDim2.new(0, 12, 0.5, -18),
	BackgroundColor3 = Color3.fromRGB(45, 40, 20),
}, topBar)
corner(coinPill, 18)
stroke(coinPill, Color3.fromRGB(255, 210, 90), 1.5, 0.3)
local coinsLabel = make("TextLabel", {
	Size = UDim2.new(1, 0, 1, 0),
	BackgroundTransparency = 1,
	Font = Enum.Font.GothamBold,
	TextSize = 20,
	TextColor3 = Color3.fromRGB(255, 215, 90),
	Text = "🪙 0",
}, coinPill)

local brawlerLabel = make("TextLabel", {
	Size = UDim2.new(0, 300, 1, 0),
	Position = UDim2.new(0.5, -150, 0, 0),
	BackgroundTransparency = 1,
	Font = Enum.Font.GothamBold,
	TextSize = 20,
	TextColor3 = Color3.fromRGB(255, 255, 255),
	Text = "Brawler: Shelly",
}, topBar)

-- Estado da partida
local matchLabel = make("TextLabel", {
	Size = UDim2.new(0, 380, 0, 30),
	Position = UDim2.new(0.5, -190, 0, 62),
	BackgroundColor3 = Color3.fromRGB(20, 22, 30),
	BackgroundTransparency = 0.25,
	Font = Enum.Font.GothamBold,
	TextSize = 18,
	TextColor3 = Color3.fromRGB(190, 235, 255),
	Text = "Aguardando...",
}, gui)
corner(matchLabel, 10)
stroke(matchLabel, Color3.fromRGB(120, 180, 255), 1.2, 0.5)

-- Placar
local scoreFrame = make("TextLabel", {
	Size = UDim2.new(0, 230, 0, 130),
	Position = UDim2.new(1, -242, 0, 96),
	BackgroundColor3 = Color3.fromRGB(20, 22, 30),
	BackgroundTransparency = 0.25,
	Font = Enum.Font.GothamMedium,
	TextSize = 16,
	TextColor3 = Color3.fromRGB(235, 235, 235),
	TextXAlignment = Enum.TextXAlignment.Left,
	TextYAlignment = Enum.TextYAlignment.Top,
	Text = "",
}, gui)
corner(scoreFrame, 10)
stroke(scoreFrame, Color3.fromRGB(60, 65, 85), 1, 0.4)
make("UIPadding", { PaddingLeft = UDim.new(0, 12), PaddingTop = UDim.new(0, 8) }, scoreFrame)

-- Barra de VIDA (embaixo, centro)
local healthBg = make("Frame", {
	Size = UDim2.new(0, 280, 0, 24),
	Position = UDim2.new(0.5, -140, 1, -54),
	BackgroundColor3 = Color3.fromRGB(18, 18, 26),
}, gui)
corner(healthBg, 12)
stroke(healthBg, Color3.fromRGB(0, 0, 0), 2, 0.3)
local healthFill = make("Frame", {
	Size = UDim2.new(1, 0, 1, 0),
	BackgroundColor3 = Color3.fromRGB(80, 220, 100),
	BorderSizePixel = 0,
}, healthBg)
corner(healthFill, 12)
gradient(healthFill, Color3.fromRGB(120, 255, 140), Color3.fromRGB(60, 190, 90))
local healthText = make("TextLabel", {
	Size = UDim2.new(1, 0, 1, 0),
	BackgroundTransparency = 1,
	Font = Enum.Font.GothamBold,
	TextSize = 15,
	TextColor3 = Color3.fromRGB(255, 255, 255),
	TextStrokeTransparency = 0.4,
	Text = "100 / 100",
}, healthBg)

-- Aviso (toast)
local toast = make("TextLabel", {
	Size = UDim2.new(0, 440, 0, 38),
	Position = UDim2.new(0.5, -220, 0.74, 0),
	BackgroundColor3 = Color3.fromRGB(30, 32, 44),
	Font = Enum.Font.GothamBold,
	TextSize = 18,
	TextColor3 = Color3.fromRGB(255, 255, 255),
	Text = "",
	TextTransparency = 1,
}, gui)
toast.BackgroundTransparency = 1
corner(toast, 10)

-- Botão da loja
local shopBtn = make("TextButton", {
	Size = UDim2.new(0, 120, 0, 38),
	Position = UDim2.new(1, -132, 0.5, -19),
	BackgroundColor3 = Color3.fromRGB(95, 125, 255),
	Font = Enum.Font.GothamBold,
	TextSize = 18,
	TextColor3 = Color3.fromRGB(255, 255, 255),
	Text = "🛒 Loja (B)",
}, topBar)
corner(shopBtn, 10)
gradient(shopBtn, Color3.fromRGB(120, 150, 255), Color3.fromRGB(80, 100, 230))
stroke(shopBtn, Color3.fromRGB(180, 200, 255), 1.2, 0.3)

-- Botões de combate
local attackBtn = make("TextButton", {
	Size = UDim2.new(0, 120, 0, 120),
	Position = UDim2.new(1, -140, 1, -150),
	BackgroundColor3 = Color3.fromRGB(225, 70, 70),
	Font = Enum.Font.GothamBold,
	TextSize = 19,
	TextColor3 = Color3.fromRGB(255, 255, 255),
	Text = "ATIRAR",
	AutoButtonColor = true,
}, gui)
corner(attackBtn, 60)
gradient(attackBtn, Color3.fromRGB(255, 100, 100), Color3.fromRGB(200, 45, 45))
stroke(attackBtn, Color3.fromRGB(255, 180, 180), 2, 0.2)

local specialBtn = make("TextButton", {
	Size = UDim2.new(0, 96, 0, 96),
	Position = UDim2.new(1, -266, 1, -138),
	BackgroundColor3 = Color3.fromRGB(245, 195, 50),
	Font = Enum.Font.GothamBold,
	TextSize = 16,
	TextColor3 = Color3.fromRGB(50, 35, 0),
	Text = "SUPER\n(Q)",
	ClipsDescendants = true,
}, gui)
corner(specialBtn, 48)
gradient(specialBtn, Color3.fromRGB(255, 225, 90), Color3.fromRGB(230, 170, 30))
stroke(specialBtn, Color3.fromRGB(255, 235, 160), 2, 0.2)
-- sombra do cooldown do super (desce conforme recarrega)
local superCd = make("Frame", {
	Size = UDim2.new(1, 0, 0, 0),
	Position = UDim2.new(0, 0, 0, 0),
	BackgroundColor3 = Color3.fromRGB(0, 0, 0),
	BackgroundTransparency = 0.45,
	BorderSizePixel = 0,
	ZIndex = 2,
}, specialBtn)

-- ===================================================================
-- LOJA
-- ===================================================================
local shopOpen = false
local shopFrame = make("Frame", {
	Size = UDim2.new(0, 470, 0, 400),
	Position = UDim2.new(0.5, -235, 0.5, -200),
	BackgroundColor3 = Color3.fromRGB(26, 28, 40),
	Visible = false,
}, gui)
corner(shopFrame, 14)
stroke(shopFrame, Color3.fromRGB(90, 120, 255), 2, 0.2)
gradient(shopFrame, Color3.fromRGB(34, 37, 54), Color3.fromRGB(22, 24, 36))

make("TextLabel", {
	Size = UDim2.new(1, 0, 0, 46),
	BackgroundTransparency = 1,
	Font = Enum.Font.GothamBold,
	TextSize = 24,
	TextColor3 = Color3.fromRGB(255, 255, 255),
	Text = "🛒 LOJA DE BRAWLERS",
}, shopFrame)

local closeBtn = make("TextButton", {
	Size = UDim2.new(0, 36, 0, 36),
	Position = UDim2.new(1, -44, 0, 6),
	BackgroundColor3 = Color3.fromRGB(225, 70, 70),
	Font = Enum.Font.GothamBold,
	TextSize = 20,
	TextColor3 = Color3.fromRGB(255, 255, 255),
	Text = "X",
}, shopFrame)
corner(closeBtn, 10)

local list = make("ScrollingFrame", {
	Size = UDim2.new(1, -20, 1, -58),
	Position = UDim2.new(0, 10, 0, 50),
	BackgroundTransparency = 1,
	BorderSizePixel = 0,
	ScrollBarThickness = 6,
	CanvasSize = UDim2.new(0, 0, 0, 0),
	AutomaticCanvasSize = Enum.AutomaticSize.Y,
}, shopFrame)
make("UIListLayout", { Padding = UDim.new(0, 8), SortOrder = Enum.SortOrder.LayoutOrder }, list)

local function refreshShop()
	for _, child in ipairs(list:GetChildren()) do
		if child:IsA("Frame") then
			child:Destroy()
		end
	end

	local names = {}
	for name in pairs(Brawlers) do
		table.insert(names, name)
	end
	table.sort(names, function(a, b) return Brawlers[a].Price < Brawlers[b].Price end)

	for _, name in ipairs(names) do
		local b = Brawlers[name]
		local owned = table.find(myData.Owned, name) ~= nil
		local selected = (myData.Selected == name)

		local row = make("Frame", {
			Size = UDim2.new(1, -6, 0, 64),
			BackgroundColor3 = Color3.fromRGB(38, 41, 56),
		}, list)
		corner(row, 10)
		stroke(row, Color3.fromRGB(60, 65, 85), 1, 0.4)

		local swatch = make("Frame", {
			Size = UDim2.new(0, 44, 0, 44),
			Position = UDim2.new(0, 12, 0.5, -22),
			BackgroundColor3 = b.Color,
		}, row)
		corner(swatch, 10)
		stroke(swatch, Color3.fromRGB(255, 255, 255), 1.5, 0.5)

		make("TextLabel", {
			Size = UDim2.new(0, 210, 1, 0),
			Position = UDim2.new(0, 66, 0, 0),
			BackgroundTransparency = 1,
			Font = Enum.Font.GothamBold,
			TextSize = 17,
			TextColor3 = Color3.fromRGB(255, 255, 255),
			TextXAlignment = Enum.TextXAlignment.Left,
			Text = b.DisplayName .. "\n❤️" .. b.Health .. "   ⚔️" .. b.Damage .. "   🎯" .. b.Range,
		}, row)

		local btn = make("TextButton", {
			Size = UDim2.new(0, 120, 0, 42),
			Position = UDim2.new(1, -132, 0.5, -21),
			Font = Enum.Font.GothamBold,
			TextSize = 16,
			TextColor3 = Color3.fromRGB(255, 255, 255),
		}, row)
		corner(btn, 10)

		if selected then
			btn.Text = "✔ EM USO"
			btn.BackgroundColor3 = Color3.fromRGB(60, 170, 95)
		elseif owned then
			btn.Text = "USAR"
			btn.BackgroundColor3 = Color3.fromRGB(80, 120, 220)
			btn.MouseButton1Click:Connect(function()
				selectEvent:FireServer(name)
			end)
		else
			btn.Text = "🪙 " .. b.Price
			btn.BackgroundColor3 = Color3.fromRGB(230, 170, 40)
			btn.MouseButton1Click:Connect(function()
				buyEvent:FireServer(name)
			end)
		end
	end
end

local function toggleShop()
	shopOpen = not shopOpen
	shopFrame.Visible = shopOpen
	if shopOpen then
		refreshShop()
	end
end

shopBtn.MouseButton1Click:Connect(toggleShop)
closeBtn.MouseButton1Click:Connect(toggleShop)

-- ===================================================================
-- CONTROLES
-- ===================================================================
local function getAimDirection()
	local char = player.Character
	local root = char and char:FindFirstChild("HumanoidRootPart")
	if not root then
		return nil
	end
	-- mira no ponto do chão (na altura do personagem) embaixo do cursor,
	-- mesmo que não tenha nenhuma peça ali (resolve o "clico aqui e vai pra lá")
	local ray = mouse.UnitRay
	local origin, dirv = ray.Origin, ray.Direction
	if math.abs(dirv.Y) > 1e-4 then
		local t = (root.Position.Y - origin.Y) / dirv.Y
		if t > 0 then
			local hit = origin + dirv * t
			local d = Vector3.new(hit.X - root.Position.X, 0, hit.Z - root.Position.Z)
			if d.Magnitude > 0.1 then
				return d.Unit
			end
		end
	end
	local look = root.CFrame.LookVector
	return Vector3.new(look.X, 0, look.Z).Unit
end

local function doAttack()
	local dir = getAimDirection()
	if dir then
		attackEvent:FireServer(dir)
	end
end

local function doSpecial()
	if os.clock() < superCooldownUntil then
		return
	end
	local dir = getAimDirection()
	if dir then
		specialEvent:FireServer(dir)
		local b = Brawlers[myData.Selected]
		local cd = b and b.Special and b.Special.Cooldown or 8
		superCooldownTotal = cd
		superCooldownUntil = os.clock() + cd
	end
end

attackBtn.MouseButton1Click:Connect(doAttack)
specialBtn.MouseButton1Click:Connect(doSpecial)

UserInputService.InputBegan:Connect(function(input, processed)
	if processed then
		return
	end
	if input.UserInputType == Enum.UserInputType.MouseButton1 then
		doAttack()
	elseif input.KeyCode == Enum.KeyCode.Q then
		doSpecial()
	elseif input.KeyCode == Enum.KeyCode.B then
		toggleShop()
	end
end)

-- ===================================================================
-- LOOP DA INTERFACE (vida + cooldown do super)
-- ===================================================================
RunService.RenderStepped:Connect(function()
	-- barra de vida
	local char = player.Character
	local hum = char and char:FindFirstChildOfClass("Humanoid")
	if hum and hum.Health > 0 then
		local ratio = hum.MaxHealth > 0 and math.clamp(hum.Health / hum.MaxHealth, 0, 1) or 0
		healthFill.Size = UDim2.new(ratio, 0, 1, 0)
		healthText.Text = math.floor(hum.Health) .. " / " .. math.floor(hum.MaxHealth)
		healthBg.Visible = true
	else
		healthBg.Visible = false
	end

	-- cooldown do super
	local remaining = superCooldownUntil - os.clock()
	if remaining > 0 then
		local r = math.clamp(remaining / superCooldownTotal, 0, 1)
		superCd.Size = UDim2.new(1, 0, r, 0)
		specialBtn.Text = string.format("%.1fs", remaining)
	else
		superCd.Size = UDim2.new(1, 0, 0, 0)
		specialBtn.Text = "SUPER\n(Q)"
	end
end)

-- ===================================================================
-- EFEITO VISUAL DO TIRO (flash + traçado + impacto)
-- ===================================================================
fxEvent.OnClientEvent:Connect(function(origin, direction, range, color)
	-- traçado
	local beam = make("Part", {
		Anchored = true,
		CanCollide = false,
		CanQuery = false,
		Material = Enum.Material.Neon,
		Color = color,
		Size = Vector3.new(0.45, 0.45, range),
		CFrame = CFrame.lookAt(origin + direction * (range / 2), origin + direction * range),
	}, workspace)
	task.spawn(function()
		for i = 1, 6 do
			beam.Transparency = i / 6
			task.wait(0.02)
		end
		beam:Destroy()
	end)

	-- flash na ponta do cano
	local flash = make("Part", {
		Anchored = true,
		CanCollide = false,
		CanQuery = false,
		Shape = Enum.PartType.Ball,
		Material = Enum.Material.Neon,
		Color = color,
		Size = Vector3.new(2.2, 2.2, 2.2),
		CFrame = CFrame.new(origin + direction * 2),
	}, workspace)
	Debris:AddItem(flash, 0.08)
end)

-- impacto + número de dano quando alguém é atingido
hitEvent.OnClientEvent:Connect(function(position, damage, color)
	-- faísca de impacto
	local spark = make("Part", {
		Anchored = true,
		CanCollide = false,
		CanQuery = false,
		Shape = Enum.PartType.Ball,
		Material = Enum.Material.Neon,
		Color = color,
		Size = Vector3.new(1.6, 1.6, 1.6),
		CFrame = CFrame.new(position),
	}, workspace)
	task.spawn(function()
		for i = 1, 5 do
			spark.Size = spark.Size + Vector3.new(0.5, 0.5, 0.5)
			spark.Transparency = i / 5
			task.wait(0.02)
		end
		spark:Destroy()
	end)

	-- número de dano subindo
	local holder = make("Part", {
		Anchored = true,
		CanCollide = false,
		CanQuery = false,
		Transparency = 1,
		Size = Vector3.new(0.2, 0.2, 0.2),
		CFrame = CFrame.new(position + Vector3.new(math.random(-10, 10) / 10, 2, 0)),
	}, workspace)
	local bb = make("BillboardGui", {
		Size = UDim2.new(0, 80, 0, 40),
		AlwaysOnTop = true,
		Adornee = holder,
	}, holder)
	local dmgLabel = make("TextLabel", {
		Size = UDim2.new(1, 0, 1, 0),
		BackgroundTransparency = 1,
		Font = Enum.Font.GothamBlack,
		TextSize = 26,
		TextColor3 = Color3.fromRGB(255, 230, 120),
		TextStrokeTransparency = 0.2,
		Text = "-" .. math.floor(damage),
	}, bb)
	task.spawn(function()
		for i = 1, 14 do
			holder.CFrame = holder.CFrame + Vector3.new(0, 0.18, 0)
			dmgLabel.TextTransparency = i / 14
			dmgLabel.TextStrokeTransparency = 0.2 + (i / 14) * 0.8
			task.wait(0.03)
		end
		holder:Destroy()
	end)
end)

-- ===================================================================
-- DADOS DO SERVIDOR
-- ===================================================================
syncEvent.OnClientEvent:Connect(function(data)
	myData = data
	coinsLabel.Text = "🪙 " .. data.Coins
	local b = Brawlers[data.Selected]
	brawlerLabel.Text = "Brawler: " .. (b and b.DisplayName or data.Selected)
	if shopOpen then
		refreshShop()
	end
end)

matchEvent.OnClientEvent:Connect(function(state)
	if state.Phase == "COUNTDOWN" then
		matchLabel.Text = "⚔️ Começa em " .. (state.Countdown or "?") .. "s..."
	elseif state.Phase == "MATCH" then
		matchLabel.Text = "🗺️ " .. state.MapName .. "   ⏱️ " .. state.TimeLeft .. "s   🎯 " .. state.KillsToWin
	else
		matchLabel.Text = state.Winner and ("🏆 Vencedor: " .. state.Winner) or "🏠 No lobby — aguardando..."
	end

	local txt = "🏅 PLACAR\n"
	for i, entry in ipairs(state.Scores or {}) do
		txt ..= i .. ". " .. entry.Name .. " — " .. entry.Kills .. "\n"
		if i >= 5 then
			break
		end
	end
	scoreFrame.Text = txt
end)

local toastTween
notifyEvent.OnClientEvent:Connect(function(message)
	toast.Text = message
	toast.TextTransparency = 0
	toast.BackgroundTransparency = 0.15
	local id = tick()
	toastTween = id
	task.delay(2.5, function()
		if toastTween == id then
			for a = 0, 1, 0.1 do
				toast.TextTransparency = a
				toast.BackgroundTransparency = 0.15 + a * 0.85
				task.wait(0.03)
			end
		end
	end)
end)

print("[BrawlArena] Cliente pronto ✔")
