--[[
	Client (LocalScript)
	Monta a interface inteira por código e cuida dos controles do jogador.
	Funciona no PC (mouse + tecla Q) e no celular (botões na tela).

	Local no Studio: StarterPlayer > StarterPlayerScripts > Client
	(Com Rojo este arquivo vira um LocalScript por causa do .client)
]]

local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local UserInputService = game:GetService("UserInputService")
local RunService = game:GetService("RunService")
local Debris = game:GetService("Debris")

local player = Players.LocalPlayer
local mouse = player:GetMouse()

local Shared = ReplicatedStorage:WaitForChild("Shared")
local Brawlers = require(Shared.Brawlers)
local Net = require(Shared.Net)

-- remotes
local attackEvent = Net.Event("Attack")
local specialEvent = Net.Event("Special")
local buyEvent = Net.Event("BuyBrawler")
local selectEvent = Net.Event("SelectBrawler")
local syncEvent = Net.Event("Sync")
local matchEvent = Net.Event("Match")
local notifyEvent = Net.Event("Notify")
local fxEvent = Net.Event("AttackFX")

local myData = { Coins = 0, Owned = {}, Selected = "Shelly" }

-- ===================================================================
-- HELPERS DE UI
-- ===================================================================
local function corner(parent, radius)
	local c = Instance.new("UICorner")
	c.CornerRadius = UDim.new(0, radius or 8)
	c.Parent = parent
	return c
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
-- CRIA A INTERFACE
-- ===================================================================
local gui = make("ScreenGui", {
	Name = "HUD",
	ResetOnSpawn = false,
	IgnoreGuiInset = true,
	ZIndexBehavior = Enum.ZIndexBehavior.Sibling,
}, player:WaitForChild("PlayerGui"))

-- Barra superior: moedas + brawler atual
local topBar = make("Frame", {
	Size = UDim2.new(1, 0, 0, 50),
	BackgroundColor3 = Color3.fromRGB(20, 22, 30),
	BackgroundTransparency = 0.2,
	BorderSizePixel = 0,
}, gui)

local coinsLabel = make("TextLabel", {
	Size = UDim2.new(0, 220, 1, 0),
	Position = UDim2.new(0, 12, 0, 0),
	BackgroundTransparency = 1,
	Font = Enum.Font.GothamBold,
	TextSize = 22,
	TextColor3 = Color3.fromRGB(255, 215, 90),
	TextXAlignment = Enum.TextXAlignment.Left,
	Text = "🪙 0",
}, topBar)

local brawlerLabel = make("TextLabel", {
	Size = UDim2.new(0, 300, 1, 0),
	Position = UDim2.new(0.5, -150, 0, 0),
	BackgroundTransparency = 1,
	Font = Enum.Font.GothamBold,
	TextSize = 20,
	TextColor3 = Color3.fromRGB(255, 255, 255),
	Text = "Brawler: Shelly",
}, topBar)

-- Estado da partida (centro-topo, abaixo da barra)
local matchLabel = make("TextLabel", {
	Size = UDim2.new(0, 360, 0, 28),
	Position = UDim2.new(0.5, -180, 0, 56),
	BackgroundColor3 = Color3.fromRGB(20, 22, 30),
	BackgroundTransparency = 0.3,
	Font = Enum.Font.GothamBold,
	TextSize = 18,
	TextColor3 = Color3.fromRGB(180, 230, 255),
	Text = "Aguardando...",
}, gui)
corner(matchLabel)

-- Placar (canto superior direito)
local scoreFrame = make("TextLabel", {
	Size = UDim2.new(0, 220, 0, 120),
	Position = UDim2.new(1, -232, 0, 90),
	BackgroundColor3 = Color3.fromRGB(20, 22, 30),
	BackgroundTransparency = 0.3,
	Font = Enum.Font.GothamMedium,
	TextSize = 16,
	TextColor3 = Color3.fromRGB(230, 230, 230),
	TextXAlignment = Enum.TextXAlignment.Left,
	TextYAlignment = Enum.TextYAlignment.Top,
	Text = "",
}, gui)
corner(scoreFrame)
make("UIPadding", { PaddingLeft = UDim.new(0, 10), PaddingTop = UDim.new(0, 6) }, scoreFrame)

-- Aviso (toast) na parte de baixo
local toast = make("TextLabel", {
	Size = UDim2.new(0, 420, 0, 36),
	Position = UDim2.new(0.5, -210, 0.78, 0),
	BackgroundColor3 = Color3.fromRGB(30, 32, 44),
	BackgroundTransparency = 0.15,
	Font = Enum.Font.GothamBold,
	TextSize = 18,
	TextColor3 = Color3.fromRGB(255, 255, 255),
	Text = "",
	TextTransparency = 1,
}, gui)
toast.BackgroundTransparency = 1
corner(toast)

-- Botão da loja (canto superior direito da barra)
local shopBtn = make("TextButton", {
	Size = UDim2.new(0, 110, 0, 36),
	Position = UDim2.new(1, -122, 0, 7),
	BackgroundColor3 = Color3.fromRGB(90, 120, 255),
	Font = Enum.Font.GothamBold,
	TextSize = 18,
	TextColor3 = Color3.fromRGB(255, 255, 255),
	Text = "🛒 Loja",
}, topBar)
corner(shopBtn)

-- Botões de combate (úteis principalmente no celular)
local attackBtn = make("TextButton", {
	Size = UDim2.new(0, 110, 0, 110),
	Position = UDim2.new(1, -130, 1, -130),
	BackgroundColor3 = Color3.fromRGB(220, 70, 70),
	Font = Enum.Font.GothamBold,
	TextSize = 18,
	TextColor3 = Color3.fromRGB(255, 255, 255),
	Text = "ATIRAR",
}, gui)
corner(attackBtn, 55)

local specialBtn = make("TextButton", {
	Size = UDim2.new(0, 90, 0, 90),
	Position = UDim2.new(1, -250, 1, -120),
	BackgroundColor3 = Color3.fromRGB(240, 190, 50),
	Font = Enum.Font.GothamBold,
	TextSize = 16,
	TextColor3 = Color3.fromRGB(40, 30, 0),
	Text = "SUPER (Q)",
}, gui)
corner(specialBtn, 45)

-- ===================================================================
-- LOJA
-- ===================================================================
local shopOpen = false
local shopFrame = make("Frame", {
	Size = UDim2.new(0, 460, 0, 380),
	Position = UDim2.new(0.5, -230, 0.5, -190),
	BackgroundColor3 = Color3.fromRGB(25, 27, 38),
	Visible = false,
}, gui)
corner(shopFrame, 12)

make("TextLabel", {
	Size = UDim2.new(1, 0, 0, 44),
	BackgroundTransparency = 1,
	Font = Enum.Font.GothamBold,
	TextSize = 24,
	TextColor3 = Color3.fromRGB(255, 255, 255),
	Text = "🛒 LOJA DE BRAWLERS",
}, shopFrame)

local closeBtn = make("TextButton", {
	Size = UDim2.new(0, 34, 0, 34),
	Position = UDim2.new(1, -42, 0, 6),
	BackgroundColor3 = Color3.fromRGB(220, 70, 70),
	Font = Enum.Font.GothamBold,
	TextSize = 20,
	TextColor3 = Color3.fromRGB(255, 255, 255),
	Text = "X",
}, shopFrame)
corner(closeBtn, 8)

local list = make("ScrollingFrame", {
	Size = UDim2.new(1, -20, 1, -56),
	Position = UDim2.new(0, 10, 0, 48),
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

	-- ordena por preço
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
			Size = UDim2.new(1, -6, 0, 60),
			BackgroundColor3 = Color3.fromRGB(35, 38, 52),
		}, list)
		corner(row)

		make("Frame", {
			Size = UDim2.new(0, 40, 0, 40),
			Position = UDim2.new(0, 10, 0.5, -20),
			BackgroundColor3 = b.Color,
		}, row)
		make("TextLabel", {
			Size = UDim2.new(0, 200, 1, 0),
			Position = UDim2.new(0, 60, 0, 0),
			BackgroundTransparency = 1,
			Font = Enum.Font.GothamBold,
			TextSize = 17,
			TextColor3 = Color3.fromRGB(255, 255, 255),
			TextXAlignment = Enum.TextXAlignment.Left,
			Text = b.DisplayName .. "\n❤️" .. b.Health .. "  ⚔️" .. b.Damage,
		}, row)

		local btn = make("TextButton", {
			Size = UDim2.new(0, 120, 0, 40),
			Position = UDim2.new(1, -130, 0.5, -20),
			Font = Enum.Font.GothamBold,
			TextSize = 16,
			TextColor3 = Color3.fromRGB(255, 255, 255),
		}, row)
		corner(btn)

		if selected then
			btn.Text = "✔ EM USO"
			btn.BackgroundColor3 = Color3.fromRGB(60, 160, 90)
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
-- CONTROLES DE COMBATE
-- ===================================================================
-- direção de mira: aponta pro mouse (PC) ou pra onde o personagem olha (celular)
local function getAimDirection()
	local char = player.Character
	local root = char and char:FindFirstChild("HumanoidRootPart")
	if not root then
		return nil
	end
	if mouse.Target then
		local dir = mouse.Hit.Position - root.Position
		dir = Vector3.new(dir.X, 0, dir.Z)
		if dir.Magnitude > 0.1 then
			return dir.Unit
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
	local dir = getAimDirection()
	if dir then
		specialEvent:FireServer(dir)
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
-- EFEITO VISUAL DO TIRO
-- ===================================================================
fxEvent.OnClientEvent:Connect(function(origin, direction, range, color)
	local beam = make("Part", {
		Anchored = true,
		CanCollide = false,
		CanQuery = false,
		Material = Enum.Material.Neon,
		Color = color,
		Size = Vector3.new(0.3, 0.3, range),
		CFrame = CFrame.lookAt(origin + direction * (range / 2), origin + direction * range),
	}, workspace)
	Debris:AddItem(beam, 0.12)
end)

-- ===================================================================
-- RECEBE DADOS DO SERVIDOR
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
		matchLabel.Text = "Começa em " .. (state.Countdown or "?") .. "s..."
	elseif state.Phase == "MATCH" then
		matchLabel.Text = "🗺️ " .. state.MapName .. "  |  ⏱️ " .. state.TimeLeft .. "s  |  🎯 " .. state.KillsToWin
	else
		matchLabel.Text = state.Winner and ("🏆 Vencedor: " .. state.Winner) or "No lobby — aguardando partida"
	end

	-- placar
	local txt = "🏅 PLACAR\n"
	for i, entry in ipairs(state.Scores or {}) do
		txt ..= i .. ". " .. entry.Name .. " — " .. entry.Kills .. "\n"
		if i >= 5 then
			break
		end
	end
	scoreFrame.Text = txt
end)

-- toast com fade
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
