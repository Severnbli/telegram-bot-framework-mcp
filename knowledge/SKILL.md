---
name: telegrambotbase
description: Build Telegram bots with the TelegramBotBase .NET framework (forms, controls, builder, navigation, state, DI). Written for 8.0.0-preview.2 (development branch).
---

> **Version note:** this guide describes TelegramBotBase **8.0.0-preview.2** (git commit `6780abf8`, `development` branch).
> It uses the request-dispatcher builder stage that does not exist in 7.x. Source paths in section 24 are checked
> against the pinned source in CI (`tests/check_guide.py`).

﻿# SKILL: Building a custom Telegram bot with the TelegramBotBase framework

> Applies to: **TelegramBotBase** (NuGet `TelegramBotBase`, GitHub `MajMcCloud/TelegramBotFramework`).
> The library targets `netcoreapp3.1 / net7 / net8 / net9 / net10.0` and sits on top of **Telegram.Bot** (v22.10.x in current source).
> Companion NuGet packages: `TelegramBotBase.Extensions.Images`, `TelegramBotBase.Extensions.Images.IronSoftware`,
> `TelegramBotBase.Extensions.ActionManager`, `TelegramBotBase.Extensions.Serializer.Database.MSSQL`,
> `TelegramBotBase.Extensions.Serializer.Database.PostgreSql`, `TelegramBotBase.Extensions.Serializer.Legacy.NewtonsoftJson`.

---

## 1. Mental model — the four core concepts

| Concept | Type | What it is |
|---|---|---|
| **Bot** | `BotBase` (sealed, created only via builder) | Root object. Owns sessions, bot commands, message loop factory, request dispatcher, state machine. Raises global events. |
| **Session** | `IDeviceSession` / `DeviceSession` | One per *chat* (user, group, channel). Keyed by chat id (`DeviceId`, negative for groups/channels). Holds `ActiveForm`, `PreviousForm`, `LastMessage`. |
| **Form** | `FormBase` (and subclasses) | The unit of UI + logic. Like a "page" or "screen". One active form per session. Everything you build is a form. |
| **Control** | `ControlBase` (and subclasses) | Reusable, stateful UI component attached to a form (`ButtonGrid`, `Label`, `TreeView`, `CalendarPicker`, …). |

**"Context sensitive"** means: the bot keeps a per-chat conversation state (which form is active, plus form fields),
and every incoming update is routed to that active form. Navigation between forms is explicit and synchronous.

Message flow per update:

```
Telegram update
  → MessageClient (long polling)
  → RequestDispatcher (rate limit / retry)
  → BotBase.Client_MessageLoop
      → get-or-create IDeviceSession
      → loop (max ESettings.NavigationMaximum = 10):
            MessageLoopFactory.MessageLoop(bot, session, UpdateResult, MessageResult)
              → FormBaseMessageLoop: bot commands → PreLoad → LoadControls → Load → SentData
                                      → Edited → ActionControls → Action → RenderControls → Render
            repeat while session.FormSwitched
```

---

## 2. Project setup

```bash
dotnet new console -n MyBot
cd MyBot
dotnet add package TelegramBotBase          # take the latest stable
```

`.csproj` minimum:

```xml
<PropertyGroup>
  <OutputType>Exe</OutputType>
  <TargetFramework>net8.0</TargetFramework>
  <ImplicitUsings>enable</ImplicitUsings>
  <Nullable>enable</Nullable>
</PropertyGroup>
```

Get an API key from **@BotFather** (`/newbot`). Never hard-code it:

```csharp
var apiKey = Environment.GetEnvironmentVariable("API_KEY")
             ?? throw new Exception("API_KEY is not set");
```

### 2.1 Copy-paste template: a new bot in 5 minutes

Three files and a working bot. It has `/start`, a main menu that cleans up after itself, a form that takes text
input and error logging.

**`Program.cs`**

```csharp
using MyBot.Forms;
using TelegramBotBase.Builder;

var apiKey = Environment.GetEnvironmentVariable("API_KEY")
             ?? throw new Exception("API_KEY is not set");

var bot = BotBaseBuilder
    .Create()
    .WithAPIKey(apiKey)
    .DefaultMessageLoop()
    .WithStartForm<StartForm>()
    .NoProxy()
    .UseDefaultRequestDispatcher()
    .CustomCommands(c =>
    {
        c.Start("Starts the bot");
        c.Add("menu", "Opens the main menu");
    })
    .UseJSON(Path.Combine(AppContext.BaseDirectory, "states.json"))
    .UseEnglish()
    .UseSingleThread()
    .Build();

bot.BotCommand += async (s, e) =>
{
    switch (e.Command)
    {
        case "/start":
            await e.Device.ActiveForm.NavigateTo(new StartForm());
            e.Handled = true;
            break;
        case "/menu":
            await e.Device.ActiveForm.NavigateTo(new MenuForm());
            e.Handled = true;
            break;
    }
};

bot.Exception += (s, e) => Console.Error.WriteLine($"[{e.DeviceId}] {e.Error}");

await bot.UploadBotCommands();
await bot.Start();

Console.WriteLine("Bot running. Press ENTER to stop.");
Console.ReadLine();
await bot.Stop();
```

**`Forms/StartForm.cs`**: the entry point. It greets the user and goes on to the menu.

```csharp
using TelegramBotBase.Base;
using TelegramBotBase.Form;

namespace MyBot.Forms;

public class StartForm : FormBase
{
    public override async Task Load(MessageResult message)
    {
        await Device.Send($"Welcome, {message.Message?.From?.FirstName}!");
        await NavigateTo(new MenuForm());
    }
}
```

**`Forms/MenuForm.cs`**: the main menu, built on `AutoCleanForm` with an inline keyboard.

```csharp
using TelegramBotBase.Base;
using TelegramBotBase.Enums;
using TelegramBotBase.Form;

namespace MyBot.Forms;

public class MenuForm : AutoCleanForm
{
    public MenuForm() => DeleteMode = EDeleteMode.OnLeavingForm;

    public override async Task Action(MessageResult message)
    {
        if (message.Handled) return;
        await message.ConfirmAction();

        switch (message.RawData)
        {
            case "name":
                message.Handled = true;
                var pd = new PromptDialog("What is your name?");
                pd.Completed += async (s, e) => await Device.Send($"Nice to meet you, {pd.Value}!");
                await OpenModal(pd);
                break;

            case "about":
                message.Handled = true;
                await Device.Send("Built with TelegramBotBase.");
                break;
        }
    }

    public override async Task Render(MessageResult message)
    {
        var bf = new ButtonForm();
        bf.AddButtonRow(new ButtonBase("Tell me your name", "name"));
        bf.AddButtonRow(new ButtonBase("About", "about"),
                        new ButtonBase("GitHub", "gh", "https://github.com/MajMcCloud/TelegramBotFramework"));
        await Device.Send("Main menu:", bf);
    }
}
```

Run it:

```bash
$env:API_KEY = "123456:ABC..."   # PowerShell  (bash: export API_KEY=...)
dotnet run
```

Next steps: add forms in `Forms/`, controls (§7), DI (§12.3), hosting as a service (§17).

---

## 3. Creating the bot — the builder

`BotBaseBuilder.Create()` returns a **staged/fluent builder**; each stage returns the next interface, so the compiler
enforces the order. The canonical full form:

```csharp
using TelegramBotBase.Builder;
using TelegramBotBase.Enums;

var bot = BotBaseBuilder
    .Create()
    .WithAPIKey(apiKey)                 // 1  IAPIKeySelectionStage
    .DefaultMessageLoop()               // 2  IMessageLoopSelectionStage
    .WithStartForm<StartForm>()         // 3  IStartFormSelectionStage
    .NoProxy()                          // 4  INetworkingSelectionStage
    .UseDefaultRequestDispatcher()      // 5  IRequestDispatcherSelectionStage
    .CustomCommands(a =>                // 6  IBotCommandsStage
    {
        a.Start("Starts the bot");
        a.Add("help", "Shows help");
    })
    .NoSerialization()                  // 7  ISessionSerializationStage
    .UseEnglish()                       // 8  ILanguageSelectionStage
    .UseSingleThread()                  // 9  IThreadingStage
    .Build();                           // → BotBase

await bot.UploadBotCommands();          // only needed when commands change
await bot.Start();
```

### 3.1 QuickStart (all defaults in one call)

```csharp
var bot = BotBaseBuilder.Create()
                        .QuickStart<StartForm>(apiKey)   // optional 2nd arg: throwPendingUpdates
                        .Build();
await bot.Start();
```

`QuickStart` = `DefaultMessageLoop` + `UseDefaultRequestDispatcher` + `NoProxy` + `OnlyStart` + `NoSerialization`
+ `DefaultLanguage` + `UseSingleThread`. Overloads: `QuickStart(string, Type)`, `QuickStart<T>(string)`,
`QuickStart(string, IFormFactory)`.

### 3.2 Every builder option

| Stage | Methods |
|---|---|
| API key | `WithAPIKey(string)` · `QuickStart(...)` |
| Message loop | `DefaultMessageLoop(IExternalActionManager?)` · `MinimalMessageLoop()` · `FullMessageLoop(IExternalActionManager?)` · `MiddlewareMessageLoop(l => l.UseForms()…)` · `CustomMessageLoop(IMessageLoopFactory)` · `CustomMessageLoop<T>()` |
| Start form | `WithStartForm<T>()` / `WithStartForm(Type)` · `WithServiceProvider<T>(IServiceProvider)` / `WithServiceProvider(Type, IServiceProvider)` · `WithFormFactory(IFormFactory)` |
| Networking | `NoProxy(throwPendingUpdates=false, timeoutInSeconds=60)` · `WithProxy(url,…)` · `WithHostAndPort(host, port,…)` · `WithHttpClient(HttpClient,…)` · `WithBotClient(TelegramBotClient,…)` |
| Dispatcher | `UseDefaultRequestDispatcher(RequestDispatcherSettings?)` · `UseFullRequestDispatcher(settings?)` · `UseDirectDispatcher()` · `UseCustomRequestDispatcher(IRequestDispatcher \| Func<MessageClient,IRequestDispatcher>)` |
| Commands | `NoCommands()` · `OnlyStart()` · `DefaultCommands()` (start/help/settings) · `CustomCommands(a => …)` |
| Serialization | `NoSerialization()` · `UseJSON(path?, fallbackForm?)` · `UseSimpleJSON(path?, fallbackForm?)` · `UseXML(path?, fallbackForm?)` · `UseSerialization(IStateMachine)` |
| Language | `DefaultLanguage()` · `UseEnglish/German/Persian/Russian/Ukrainian/Belarusian()` · `Custom(Localization)` |
| Threading | `UseSingleThread()` · `UseThreadPool()` · `UseThreadPool(workerThreads, ioThreads)` |

> **Ordering rule:** threading is the *last* stage — `UseSingleThread`/`UseThreadPool` read
> `MessageLoopFactory.ConfigureUpdateTypes()` to set `MessageClient.AllowedUpdates`. Custom message loops that
> subscribe to extra `UpdateType`s (e.g. `InlineQuery`) only work if the loop reports them.
> If you skip a dispatcher stage, `Build()` silently installs `DefaultRequestDispatcher`.

### 3.3 Run loop / lifetime

```csharp
await bot.Start();          // starts long polling; returns immediately
Console.ReadLine();
await bot.Stop();           // stops polling + saves session states
```

`bot.Start()` also: loads saved session states (if a state machine is configured) and, when
`ESettings.SaveSessionsOnConsoleExit` is on, registers a console handler that saves states on exit.

### 3.4 Decision guide: which option when?

**Message loop**

| Situation | Choose |
|---|---|
| Normal bot with forms, buttons and controls | `DefaultMessageLoop()` |
| Callbacks from messages sent outside a form (notifications, broadcasts) | `DefaultMessageLoop(eam)` + ActionManager (§18) |
| Very small bot that only reacts to text | `MinimalMessageLoop()` |
| Needs update types the default loop drops (polls, chat member updates, …) | `FullMessageLoop()` |
| Auth gate, logging, inline queries, custom order of steps | `MiddlewareMessageLoop(...)` |
| Completely custom pipeline | `CustomMessageLoop(IMessageLoopFactory)` |

**Request dispatcher**

| Situation | Choose |
|---|---|
| Default, small to medium bots | `UseDefaultRequestDispatcher()` (concurrency cap + 429 retry) |
| Broadcasts, many chats/groups, risk of hitting Telegram limits | `UseFullRequestDispatcher(settings)` (per-chat/per-group/global rate limits) |
| Tests or your own throttling outside the library | `UseDirectDispatcher()` |
| Logging/metrics around every API call | `UseCustomRequestDispatcher(...)` wrapping a built-in one |

**Threading**

| Situation | Choose |
|---|---|
| Default; forms use shared state; order of messages matters | `UseSingleThread()` |
| Many users at once, slow handlers (I/O, external APIs), thread-safe code | `UseThreadPool()` |

**Serialization (session state)**

| Situation | Choose |
|---|---|
| Prototype; losing state on restart is fine | `NoSerialization()` |
| Single instance, complex form fields (lists, objects) | `UseJSON(path)` |
| Single instance, only simple fields (string, int, bool) | `UseSimpleJSON(path)` |
| Existing XML tooling | `UseXML(path)` |
| Several instances / containers / a database already exists | MSSQL or PostgreSql serializer extension |
| Upgrading from an old version with Newtonsoft state files | `UseNewtonsoftJson(...)` |
| Forms created through DI (constructor parameters) | any of the above **plus** `fallbackForm` |

**Start form / form creation**

| Situation | Choose |
|---|---|
| Forms with a parameterless constructor | `WithStartForm<T>()` |
| Forms need services (DbContext, HttpClient, …) | `WithServiceProvider<T>(sp)` + `NavigateTo<T>()` |
| Own creation logic | `WithFormFactory(IFormFactory)` |

**Base class for a form**

| Situation | Choose |
|---|---|
| Menu or screen that should not leave old messages behind | `AutoCleanForm` |
| Bot used in private chats and groups | `SplitterForm` as start form |
| Group moderation (join/leave, edits) | `GroupForm` |
| Ask for one value / Yes-No / short notice | `PromptDialog` / `ConfirmDialog` / `AlertDialog` |
| Deep menus with a "Back" button | `NavigationController` |
| Anything else | `FormBase` |

---

## 4. Forms — the heart of the framework

`FormBase` lives in namespace **`TelegramBotBase.Form`** (the file is `Base/FormBase.cs`, but the namespace is `.Form`).

### 4.1 Overridable lifecycle members

| Member | Fires when | Typical use |
|---|---|---|
| `event Init` (`InitEventArgs`) | form instance initialised (once, before first open) | **create & `AddControl()` controls here** |
| `event Opened` | navigation lands on this form | one-off welcome message |
| `event Closed` | form is left/disposed | cleanup, delete leftover messages |
| `PreLoad(MessageResult)` | before `Load`, on every update | `AutoCleanForm` message cleanup happens here |
| `LoadControls` / `ActionControls` / `RenderControls` | framework-internal: fan-out to controls | don't override |
| `Load(MessageResult)` | every incoming message/action in this context | read input, mutate form state |
| `Edited(MessageResult)` | message was edited | moderation bots |
| `Action(MessageResult)` | button/callback click not handled by a control | menu dispatch |
| `SentData(DataResult)` | photo/audio/video/document/contact/location received | file handling |
| `Render(MessageResult)` | end of the cycle | send/edit the UI |
| `ReturnFromModal(ModalDialog)` | a modal child closed | react to dialog result |

**`Load` vs `Render`:** `Load` decides *state*, `Render` draws *output* from that state. This split is the idiomatic
pattern for wizards/forms (see §4.4).

### 4.2 Minimal form

```csharp
using TelegramBotBase.Base;   // MessageResult, DataResult, ControlBase
using TelegramBotBase.Form;   // FormBase, ButtonForm, ButtonBase, AutoCleanForm

public class StartForm : FormBase
{
    public StartForm()
    {
        Init   += (s, e) => Task.CompletedTask;   // AsyncEventHandler<InitEventArgs>
        Opened += async (s, e) => await Device.Send("Hello world!");
    }

    public override async Task Load(MessageResult message)
    {
        switch (message.Command)          // raw text of the message
        {
            case "hi":
            case "hello":
                await Device.Send("Hello you there!");
                break;
            case "maybe":
                await Device.Send("Maybe what?", replyTo: message.MessageId);
                break;
        }
    }

    public override async Task Render(MessageResult message)
    {
        var bf = new ButtonForm();
        bf.AddButtonRow(new ButtonBase("Open details", "details"));
        bf.AddButtonRow(new ButtonBase("Google", "google", "https://google.com")); // URL button
        await Device.Send("Pick something", bf);
    }
}
```

### 4.3 `AutoCleanForm` — the form you should usually derive from

Deletes the bot's previous messages so menus don't pile up.

```csharp
public class Menu : AutoCleanForm
{
    public Menu()
    {
        DeleteMode = EDeleteMode.OnLeavingForm;  // None | OnEveryCall (default) | OnLeavingForm
        DeleteSide = EDeleteSide.BotOnly;        // BotOnly | Both | UserOnly
    }
}
```

It tracks sent (and optionally received) message ids in a `[SaveState] public List<int> OldMessages`, and exposes
`AddMessage(int|Message)` / `LeaveMessage(int)`.

> **Caveat:** received messages are tracked via `Device.MessageReceived`, which the library never raises (§11). So
> `DeleteSide = Both` / `UserOnly` only ever deletes what the bot sent. Add `AddMessage(message.MessageId)` in `Load`
> if you really want the user's message cleaned up too.

### 4.4 Multi-step input in one form (the canonical wizard)

```csharp
public class RegistrationForm : AutoCleanForm
{
    [SaveState] public string? Firstname { get; set; }
    [SaveState] public string? Lastname  { get; set; }
    [SaveState] public string? EMail     { get; set; }

    public override Task Load(MessageResult message)
    {
        if (string.IsNullOrWhiteSpace(message.MessageText)) return Task.CompletedTask;

        if (Firstname is null) { Firstname = message.MessageText; return Task.CompletedTask; }
        if (Lastname  is null) { Lastname  = message.MessageText; return Task.CompletedTask; }
        if (EMail     is null) { EMail     = message.MessageText; return Task.CompletedTask; }

        return Task.CompletedTask;
    }

    public override async Task Render(MessageResult message)
    {
        if (Firstname is null) { await Device.Send("Please send your firstname:"); return; }
        if (Lastname  is null) { await Device.Send("Please send your lastname:");  return; }
        if (EMail     is null) { await Device.Send("Please send your email:");     return; }

        var bf = new ButtonForm();
        bf.AddButtonRow(new ButtonBase("Back", "back"));
        await Device.Send($"Name: {Firstname} {Lastname}\nMail: {EMail}", bf);
    }

    public override async Task Action(MessageResult message)
    {
        await message.ConfirmAction();
        if (message.RawData == "back")
            await NavigateTo(new Menu());
    }
}
```

### 4.5 Handling attachments

```csharp
public override async Task SentData(DataResult data)
{
    switch (data.Type)
    {
        case MessageType.Contact:
            await Device.Send($"Phone: {data.Contact.PhoneNumber}", replyTo: data.MessageId);
            break;
        case MessageType.Photo:
            var photo = InputFile.FromString(data.Photos.Last().FileId);
            await Device.SendPhoto(photo, "Your image");
            break;
        case MessageType.Document:
            await data.DownloadDocument("/tmp/upload.bin");   // or DownloadRawDocument() / DownloadRawTextDocument()
            break;
        case MessageType.Location:
            await Device.Send($"Lat {data.Location.Latitude}, Lng {data.Location.Longitude}");
            break;
    }
}
```

Convenience helpers on the session: `Device.RequestContact(...)`, `Device.RequestLocation(...)`.

---

## 5. Talking to the user — `IDeviceSession` (`Device`)

Available inside every form as `this.Device`.

```csharp
await Device.Send("plain text");
await Device.Send("with buttons", buttonForm);
await Device.Send("reply", replyTo: message.MessageId);
await Device.Send("silent", disableNotification: true);
await Device.Send("html", parseMode: ParseMode.Html);
await Device.Send("raw", markdownV2AutoEscape: false);   // default true for MarkdownV2

var m = await Device.Send("I will edit this later", bf);
await Device.Edit(m.MessageId, "edited text", bf);
await Device.Edit(m);                                    // edit keeping its text
await Device.EditReplyMarkup(m.MessageId, newBf);        // change only buttons
await Device.DeleteMessage(m);
await Device.HideReplyKeyboard();
await Device.SetAction(ChatAction.Typing);
await Device.SendPhoto(file, "caption", bf);
await Device.SendVideo(url); await Device.SendLocalVideo(path);
await Device.SendDocument(InputFile.FromStream(stream, "report.bin"), "caption");
await Device.SendTextFile("report.txt", contents);
await Device.BanUser(userId); await Device.RestrictUser(userId, perms);
await Device.GetChatUser(userId);
```

Useful properties: `DeviceId`, `ChatTitle`, `GetChatTitle()`, `LastMessage`, `LastMessageId`,
`IsGroup`, `IsChannel`, `ActiveForm`, `PreviousForm`, `LastAction`.

Escape hatches to raw Telegram.Bot:

```csharp
var me = await Device.Api(c => c.GetMe());
await Device.Dispatch(c => c.SendChatAction(device.DeviceId, ChatAction.Typing));
var ok = Device.Raw(c => c.SomeSyncCall());
// And: FormBase.API  →  API.GetMe()  (bypasses the dispatcher, use sparingly)
```

> **Source generator tip:** `TelegramBotBase.SourceGenerators` is shipped as an analyzer with the package. It emits
> `TelegramBotBase.DeviceExtensions` — extension methods on `IDeviceSession` for *every* Telegram.Bot client method
> that takes a `chatId`, auto-filling it with `device.DeviceId`. So you can write
> `await Device.SendChatAction(ChatAction.Typing)`, `await Device.GetChatMember(...)`, etc.

**Limits enforced by the library** (`TelegramBotBase.Constants.Telegram`): message text `4096`
(→ `MessageTooLongException`), callback data `64` bytes (→ `CallbackDataTooLongException`),
inline keyboard 13×8, reply keyboard 25×12.

---

## 6. Buttons and callback data

### 6.1 `ButtonForm` = a grid of buttons

```csharp
var bf = new ButtonForm();
bf.AddButtonRow("One", "v1");                                  // shorthand
bf.AddButtonRow(new ButtonBase("Two", "v2"), new ButtonBase("Three", "v3"));
bf.AddSplitted(items.Select(i => new ButtonBase(i.Title, i.Id.ToString())), 2);
bf.AddButtonRow(new ButtonBase("Docs", "docs", "https://…"));  // URL button (no callback)
await Device.Send("Menu", bf);
```

`ButtonForm` implicitly converts to `InlineKeyboardMarkup` **and** `ReplyKeyboardMarkup`.
Other members: `Rows`, `Cols`, `Count`, `GetRange(start,count)`, `FilterDuplicate(filter, byRow)`, `Duplicate()`,
`GetButtonByValue(v)`, `FindRow(text)`, `Markup`.

### 6.2 Reading a click in `Action`

```csharp
public override async Task Action(MessageResult message)
{
    if (message.Handled) return;

    await message.ConfirmAction();                 // ALWAYS answer the callback query
    // await message.ConfirmAction("Saved", showAlert: true);

    var call = message.GetData<CallbackData>();    // null if raw string was used
    if (call is null)
    {
        // raw value style:
        switch (message.RawData) { case "back": await NavigateTo(new Menu()); break; }
        return;
    }

    message.Handled = true;                        // stop further handling / Render
    switch (call.Value) { /* … */ }
}
```

Two button-value styles:
* **Raw string** — `new ButtonBase("Back", "back")` → read `message.RawData`.
* **Structured** — `new CallbackData("method", "value").Serialize()` or `CallbackData.Create("m","v")`
  → read `message.GetData<CallbackData>()` (`.Method`, `.Value`). Required by the ActionManager extension.
  `CallbackData` has an implicit `string` conversion, so `new ButtonBase("x", CallbackData.Create("m","v"))` works.

> **Always** call `message.ConfirmAction()` for callback queries, otherwise the user's client shows a spinning
> clock forever. Set `message.Handled = true` once you consumed an action so `Render` doesn't re-draw.

### 6.3 Inline vs Reply keyboards

Reply keyboards are handled as *text messages*, so they arrive in `Load` (as `message.Command`), not in `Action`.
Inline keyboards arrive as callback queries in `Action`. To use both at once, use two `ButtonGrid` controls with
different `KeyboardType` — see `Examples/InlineAndReplyCombination`.

---

## 7. Controls

Add controls inside `Init` (or the constructor) with `AddControl(c)`; the framework then drives
`Load`/`Action`/`Render` on them automatically and routes callback data prefixed `#c<id>_` to the right control.

Namespaces: **`TelegramBotBase.Controls.Inline`** (Label, ProgressBar, CalendarPicker, MonthPicker, ToggleButton,
MultiToggleButton, TreeView, TreeViewNode) and **`TelegramBotBase.Controls.Hybrid`** (ButtonGrid, TaggedButtonGrid,
CheckedButtonList, MultiView, ButtonRow).

### 7.1 ButtonGrid (the workhorse)

```csharp
private ButtonGrid _grid;

private void Init(object sender, InitEventArgs e)
{
    var bf = new ButtonForm();
    bf.AddButtonRow(new ButtonBase("Back", "back"), new ButtonBase("Switch", "switch"));
    bf.AddButtonRow(new ButtonBase("Item 1", "i1"), new ButtonBase("Item 2", "i2"));

    _grid = new ButtonGrid(bf)                    // or: new ButtonGrid { DataSource = { ButtonForm = bf } }
    {
        KeyboardType = EKeyboardType.InlineKeyBoard,   // default: ReplyKeyboard
        Title        = "Choose an option:",
        EnablePaging = true,
        EnableSearch = true,
        ResizeKeyboard = false,
        OneTimeKeyboard = false,
        MessageParseMode = ParseMode.Markdown
    };
    _grid.ButtonClicked += Grid_ButtonClicked;

    AddControl(_grid);
}

private async Task Grid_ButtonClicked(object sender, ButtonClickedEventArgs e)
{
    if (e.Button is null) return;
    if (e.Button.Value == "back") await NavigateTo(new Menu());
    else await Device.Send($"Clicked {e.Button.Text} ({e.Button.Value})");
}
```

Setting `_grid.KeyboardType` at runtime re-renders and toggles inline/reply.

### 7.2 Other controls (short recipes)

```csharp
// Label — a message you can update without tracking the id
var label = new Label("My test label"); AddControl(label);
label.Text = "*new text*";

// CalendarPicker
var picker = new CalendarPicker { Title = "Pick date" }; AddControl(picker);
DateTime d = picker.SelectedDate; var month = picker.VisibleMonth; var culture = picker.Culture;

// MonthPicker  (see eMonthPickerMode)
// TreeView
var tree = new TreeView();
var root = new TreeViewNode("Cars", "cars",
              new TreeViewNode("Porsche", "porsche",
                  new TreeViewNode("Website", "web", "https://porsche.com"),
                  new TreeViewNode("911", "911")),
              new TreeViewNode("BMW", "bmw"));
tree.Nodes.Add(root); AddControl(tree);
var sel = tree.SelectedNode; var vis = tree.VisibleNode;

// ToggleButton / MultiToggleButton
var tb = new ToggleButton { Checked = true }; tb.Toggled += (s,e) => { /* ((ToggleButton)s).Checked */ };
AddControl(tb);

// ProgressBar
var bar = new ProgressBar(0, 100, ProgressBar.EProgressStyle.squares) { Device = Device };
await bar.Render(message);  bar.Value = 42; await bar.Render(message);   // Render takes the current MessageResult

// CheckedButtonList — multi-select list, events ButtonClicked + CheckedChanged
// TaggedButtonGrid — buttons with tags (TagButtonBase), filterable
// MultiView — abstract control for switching "views" inside one form; override the view renderers
```

### 7.3 Writing your own control

```csharp
public class MyControl : ControlBase
{
    public string Title { get; set; } = "";
    private int? _messageId;

    public override void Init() { }                                  // wire up Device events
    public override Task Load(MessageResult r)  => Task.CompletedTask;
    public override async Task Action(MessageResult r, string? value = null)
    {
        await r.ConfirmAction();
        // `value` is set when the callback was routed as "#c<id>_<value>"
    }
    public override async Task Render(MessageResult r)
    {
        var bf = new ButtonForm(); bf.AddButtonRow(Title, "go");
        if (_messageId is null) _messageId = (await Device.Send(Title, bf)).MessageId;
        else await Device.Edit(_messageId.Value, Title, bf);
    }
    public override Task Hidden(bool formClose) => Task.CompletedTask;
    public override Task Cleanup() => Task.CompletedTask;            // form closed / control removed
}
```

`AddControl` assigns `Id` (`Controls.Count + 1`) and `Device` and calls `Init()`; `ControlId` is `"#c" + Id`.
`RemoveControl(c)` / `RemoveAllControls()` run `Cleanup()`.

### 7.4 More ButtonGrid options

| Property | Default | Purpose |
|---|---|---|
| `NavigationBarVisibility` | `always` | `auto` / `never` / `always` (`ENavigationBarVisibility`) for the paging bar |
| `HeadLayoutButtonRow` / `SubHeadLayoutButtonRow` | `null` | Fixed rows above the paged items (e.g. "Back") |
| `ConfirmationText` | `""` | Text used to confirm clicks |
| `DeletePreviousMessage` / `DeleteReplyMessage` | `true` | Reply-keyboard cleanup behaviour |
| `HideKeyboardOnCleanup` | `true` | Removes reply keyboard when the form closes |
| `CurrentPageIndex`, `SearchQuery`, `MessageId` | – | Runtime state |

### 7.5 Data sources (large / lazy lists)

`ButtonGrid.DataSource` is a `ButtonFormDataSource` (implicitly convertible from/to `ButtonForm`). Subclass it to page
through big or DB-backed lists without building the whole `ButtonForm`:

```csharp
public class CountryDataSource : ButtonFormDataSource
{
    private readonly List<string> _items;
    public CountryDataSource(List<string> items) => _items = items;

    public override int Count       => _items.Count;
    public override int ColumnCount => 1;
    public override int RowCount    => Count;

    public override ButtonRow ItemAt(int i) => Render(_items[i]);
    public override List<ButtonRow> ItemRange(int start, int count)
        => _items.Skip(start).Take(count).Select(Render).ToList();
    public override List<ButtonRow> AllItems() => _items.Select(Render).ToList();

    public override ButtonForm PickItems(int start, int count, string? filter = null) { /* filter + page */ }
    public override ButtonForm PickAllItems(string? filter = null) { /* … */ }
    public override int CalculateMax(string? filter = null) { /* count after filter */ }

    public override ButtonRow Render(object data) => new(new ButtonBase((string)data, (string)data));
}

_grid = new ButtonGrid { DataSource = new CountryDataSource(list), EnablePaging = true, EnableSearch = true };
```

Generic helper: `StaticDataSource<T>` (`IDataSource<T>`). Reference: `TelegramBotBase.Test/Tests/DataSources/*`.

### 7.6 MultiView (several "pages" in one control)

```csharp
public class Wizard : MultiView
{
    public override Task Action(MessageResult r, string? value = null)
    {
        if (r.RawData == "next") SelectedViewIndex++;   // setter triggers re-render
        if (r.RawData == "back") SelectedViewIndex--;
        return Task.CompletedTask;
    }

    public override async Task RenderView(RenderViewEventArgs e)
    {
        var bf = new ButtonForm();
        bf.AddButtonRow(new ButtonBase("Back", "back"), new ButtonBase("Next", "next"));
        await Device.Send($"Page {e.CurrentView + 1}", bf);
    }
}
```

`ForceRender()` redraws manually; previously sent view messages are deleted automatically.

### 7.7 Special button types

```csharp
new DynamicButton(() => $"Counter: {_count}", "inc");          // text evaluated on every render
new TagButtonBase("Apple", "apple", "fruit");                   // for TaggedButtonGrid filtering
new WebAppButtonBase("Open app", new WebAppInfo { Url = "https://my.app" }); // Telegram Mini App
```

---

## 8. Built-in dialogs

All in `TelegramBotBase.Form`. `PromptDialog`, `ConfirmDialog`, `AlertDialog` derive from `ModalDialog` and are
`[IgnoreState]`.

```csharp
// Prompt: ask for one text value
var pd = new PromptDialog("Please tell me your name?") { ShowBackButton = true, BackLabel = "Cancel" };
pd.Completed += async (s, en) => await Device.Send("Hello " + pd.Value);   // en.Value, en.Tag
await OpenModal(pd);        // modal: parent form stays alive

// Confirm: several buttons
var cd = new ConfirmDialog("Please confirm", new ButtonBase("Ok","ok"), new ButtonBase("Cancel","cancel"));
cd.AutoCloseOnClick = true;
cd.ButtonClicked += async (s, en) =>
{
    // IMPORTANT: after the dialog has closed, navigate from the dialog instance, not the (possibly disposed) parent
    await cd.NavigateTo(new NextForm());
};
await NavigateTo(cd);       // non-modal: this form is disposed

// Alert: one button
var ad = new AlertDialog("Saved!", "Ok");
ad.ButtonClicked += async (s, en) => await NavigateTo(new Menu());
await NavigateTo(ad);

// ArrayPromptDialog: a prompt that is a grid of buttons (not modal)
var ap = new ArrayPromptDialog("Pick one", new[] { new ButtonBase("A","a"), new ButtonBase("B","b") });
ap.ButtonClicked += ...; await NavigateTo(ap);
```

### 8.1 Modal vs non-modal — the rule that trips people up

* `OpenModal(modalDialog)` → parent form **stays alive**; controls get `Hidden(false)`; the dialog's `Closed`
  event restores the parent; `ReturnFromModal` is called on the parent.
* `NavigateTo(dialog)` → parent form is **closed and disposed**. Any continuation must run from the dialog's own
  context (`pd.Device.Send(...)`, `pd.NavigateTo(...)`).
* Calling `NavigateTo` **from inside a modal dialog throws** `InvalidOperationException`
  ("Cannot navigate to another form from a modal dialog"). Close it first with `CloseForm()`.
* `ModalDialog.IsDisplayedAsModal` is true when `ParentForm != null`.

Study `Examples/ModalDialogNavigation` (Version1–Version4) — it demonstrates exactly these four scenarios.

---

## 9. Navigation

### 9.1 Cross navigation (default)

```csharp
await NavigateTo(new DetailsForm(id));                 // ctor args are passed to Init via InitEventArgs
await NavigateTo(form, arg1, arg2);
```

`NavigateTo` sets `session.FormSwitched = true`, closes the current form (controls `Hidden(true)` → `Cleanup()` →
`Closed` → `DisposeAsync`), then fires `Init` + `Opened` on the target. The message loop then re-runs for the new
form — up to `ESettings.NavigationMaximum` (default 10) chained navigations per update.

Override `NavigateTo` to pass state forward automatically:

```csharp
public override Task NavigateTo(FormBase newForm, params object[] args)
{
    if (newForm is MultipleChoiceForm m) m.UserDetails = UserDetails;
    return base.NavigateTo(newForm, args);
}
```

### 9.2 Stack navigation — `NavigationController`

For "Android back button" flows (`TelegramBotBase.Form.Navigation`).

```csharp
var nc = new NavigationController(this);      // 'this' = root form you can return to
await NavigateTo(nc);
await nc.PushAsync(new Form1());

// inside a pushed form:
await NavigationController.PushAsync(next);
await NavigationController.PushAndReplaceAsync(next);   // pop current, then push
await NavigationController.PopAsync();
await NavigationController.PopToRootAsync();
```

`ForceCleanupOnLastPop = true` (default) auto-swaps the controller back to the root form when the stack shrinks to 1.
`NavigationController` is itself a `FormBase` and implements `IStateForm` (`[SaveState] History`, `Index`), so stacks
survive restarts — but only for forms with a **parameterless constructor**.

---

## 10. Bot commands

```csharp
.CustomCommands(a =>
{
    a.Start("Starts the bot");
    a.Add("myid",    "Returns my device id");
    a.Help("Help"); a.Settings("Settings");
    a.Add("scoped", "Admin only", BotCommandScope.AllChatAdministrators());
    a.Add("de",     "Deutsch",    language: "de");
    // a.Clear(); a.Remove();
})
```

Then push them to BotFather **once** (or whenever they change):

```csharp
await bot.UploadBotCommands();
```

Handle them globally:

```csharp
bot.BotCommand += async (s, en) =>
{
    switch (en.Command)
    {
        case "/form1":
            await en.Device.ActiveForm.NavigateTo(new Form1());
            en.Handled = true;                 // stops the update from also hitting the active form
            break;
        case "/params":
            await en.Device.Send("Params: " + string.Join(", ", en.Parameters),
                                 replyTo: en.Device.LastMessageId);
            en.Handled = true;
            break;
    }
};
```

`/start` is **not** special-cased by the framework — it is just a registered command you handle in `BotCommand`
(the usual handler navigates back to the start form). Commands with parameters
(`/params 1 2 3`) are exposed via `en.Parameters` and `message.BotCommandParameters`. In groups Telegram may send
`/cmd@MyBot` — the framework strips the `@…` (`message.IsBotGroupCommand` tells you it happened).
Inspection: `bot.IsKnownBotCommand("/x")`, `bot.GetBotCommands()`, `bot.GetAllBotCommands()`.

---

## 11. Global bot events and settings

```csharp
bot.SessionBegins    += (s, e) => { /* e.DeviceId, e.Device */ };
bot.BotCommand       += async (s, en) => { /* en.Command, en.Parameters, en.Handled */ };
bot.UnhandledCall    += (s, e) => { /* e.RawData (callback value), e.Command, e.DeviceId, e.MessageId */ };
bot.Exception        += (s, e) => { /* e.Error, e.DeviceId, e.Device, e.Command */ };
bot.BotRelationChanged += (s, e) => { /* user blocked/unblocked the bot, added to chat … */ };

bot.SetSetting(ESettings.NavigationMaximum, 20);          // chained navigations per update (default 10)
bot.SetSetting(ESettings.SaveSessionsOnConsoleExit, true); // default false
bot.SetSetting(ESettings.HandleRelationChanges, true);     // default true
```

> **Dead settings:** `ESettings.LogAllMessages` and `ESettings.SkipAllMessages` are only *written* to
> `SystemSettings` in the `BotBase` ctor — nothing in the library ever reads them, so they currently have no effect.
> (`ESettings.MaxNumberOfRetries` is `[Obsolete]` — use `RequestDispatcherSettings`.)

> **Dead events:** `bot.Message` (`MessageIncomeEventArgs`) is declared and `OnMessage(...)` exists, but the library
> never raises it — so it fires **zero** times, and `bot.SetSetting(ESettings.LogAllMessages, true)` does not make it
> fire. Same for `Device.MessageReceived`. Log incoming updates in a middleware step (§14) or a custom
> `IMessageLoopFactory` instead; `Device.MessageSent` and `Device.MessageDeleted` *do* fire.

`UnhandledCall` is your safety net for callback values no form handled — good place for a default
"unknown action" answer plus `await message.ConfirmAction()`.

---

## 12. Sessions, state persistence and DI

### 12.1 Sessions

```csharp
foreach (var (chatId, session) in bot.Sessions.SessionList) { … }
bot.Sessions.GetUserSessions();     // chatId > 0
bot.Sessions.GetGroupSessions();    // chatId < 0
bot.Sessions.GetSession(chatId);
await bot.Sessions.StartSession(chatId);
bot.Sessions.EndSession(chatId);
await bot.SentToAll("Maintenance in 5 minutes.");
```

### 12.2 Persisting form state across restarts

```csharp
.UseJSON()                                   // states.json in CWD, full type info (generics, objects)
.UseJSON(@"C:\data\states.json", fallbackForm: typeof(Menu))
.UseSimpleJSON()                             // basic types only
.UseXML()
.UseSerialization(myStateMachine)            // or a DB serializer from the extension packages
```

Mark what to keep:

```csharp
[SaveState] public long UserId { get; set; }

[IgnoreState]                       // never serialize this form
public class VolatileForm : FormBase { }
```

Or take full control with `IStateForm` (`LoadState(LoadStateEventArgs)` / `SaveState(SaveStateEventArgs)` —
`e.Get/GetInt/GetObject`, `e.Set(...)`).
`IStateMachine` = `SaveFormStates(SaveStatesEventArgs)` + `LoadFormStates()` for custom stores.
DB-backed options: `TelegramBotBase.Extensions.Serializer.Database.MSSQL` (`.UseSqlDatabase(...)`) /
`.PostgreSql` (`.UsePostgreSqlDatabase(...)`);
legacy Newtonsoft: `TelegramBotBase.Extensions.Serializer.Legacy.NewtonsoftJson` (`.UseNewtonsoftJson(...)`).

> Forms resolved via DI (constructor injection) cannot be re-created by the state machine — it needs a
> parameterless constructor. Provide a `fallbackForm` for those.

### 12.3 Dependency injection

```csharp
var services = new ServiceCollection()
    .AddDbContext<BotDbContext>(x => x.UseInMemoryDatabase("TelegramBotBase"))
    .AddSingleton<IWeatherService, WeatherService>();

var sp = services.BuildServiceProvider();

var bot = BotBaseBuilder.Create()
    .WithAPIKey(apiKey)
    .DefaultMessageLoop()
    .WithServiceProvider<StartForm>(sp)     // ← key call
    .NoProxy().UseDefaultRequestDispatcher().NoCommands()
    .NoSerialization().DefaultLanguage().UseSingleThread()
    .Build();
```

```csharp
using TelegramBotBase.DependencyInjection;

public class StartForm : FormBase
{
    private readonly BotDbContext _db;
    public StartForm(BotDbContext db) => _db = db;

    public override async Task Action(MessageResult message)
    {
        // DI-aware navigation: the new form gets its own service scope
        var next = await this.NavigateTo<ConfirmationForm>();
        if (next is null) await Device.Send("Could not open ConfirmationForm");
    }
}
```

Each form gets its own `IServiceScope` (created by `ServiceProviderFormFactory`) that is disposed when the form
closes — so scoped services like `DbContext` are safe per form. Navigate with the
`TelegramBotBase.DependencyInjection.Extensions` overloads (`NavigateTo<T>()` / `NavigateTo(Type)`), **not** `new T()`.
Custom factories: `DefaultFormFactory`, `LambdaFormFactory`, `ServiceProviderFormFactory`, or roll your own
`IFormFactory` (`CreateStartForm()`, `CreateForm(Type)`, `CreateForm<T>()`).

---

## 13. Groups and channels

```csharp
// Route by chat type at the entry point
public class Start : SplitterForm
{
    public override async Task<bool> Open(MessageResult e)         // private chat
    { await NavigateTo(new Menu()); return true; }

    public override async Task<bool> OpenGroup(MessageResult e)    // Group (and Supergroup fallback)
    { await NavigateTo(new GroupManageForm()); return true; }

    public override Task<bool> OpenSupergroup(MessageResult e) => base.OpenSupergroup(e);
    public override Task<bool> OpenChannel(MessageResult e)   => base.OpenChannel(e);
}
```

`SplitterForm` precedence: `OpenChannel` → `OpenSupergroup` → `OpenGroup` → `Open` (return `false` to fall through).

```csharp
public class GroupManageForm : GroupForm
{
    public override async Task OnMemberChanges(MemberChangeEventArgs e)
    {
        if (e.Type != MessageType.NewChatMembers && e.Type != MessageType.LeftChatMember) return;
        await Device.DeleteMessage(e.Result.Message);          // "join/leave" hider
    }
    public override Task OnGroupChanged(GroupChangedEventArgs e) => Task.CompletedTask;
    public override Task OnMessage(MessageResult e)   => Task.CompletedTask;
    public override Task OnMessageEdit(MessageResult e) => Task.CompletedTask;
}
```

Moderation helpers: `Device.BanUser`, `Device.UnbanUser`, `Device.RestrictUser`, `Device.ChangeChatPermissions`,
`Device.GetChatUser`. `bot.BotRelationChanged` fires when a user blocks/unblocks the bot or the bot is added to a chat
(gated by `ESettings.HandleRelationChanges`).

---

## 14. Message loops (choosing your processing pipeline)

| Loop | Update types | Notes |
|---|---|---|
| `DefaultMessageLoop()` → `FormBaseMessageLoop` | Message, EditedMessage, BusinessMessage, EditedBusinessMessage, CallbackQuery | The right default. Full form event set. |
| `MinimalMessageLoop()` | all | Only calls `Load`. Tiny bots. |
| `FullMessageLoop()` | all | Every update type, every event. |
| `MiddlewareMessageLoop(l => …)` | you decide | Composable pipeline. |
| `CustomMessageLoop(impl)` | you decide | Implement `IMessageLoopFactory`. |

### Middleware pipeline

```csharp
using TelegramBotBase.MessageLoops.Extensions;

.MiddlewareMessageLoop(ml => ml
    .Use(async (container, next) =>                 // custom middleware: auth gate
    {
        var from = container.UpdateResult.Message?.From;
        if (from is not null && Allowed(from.Id)) await next();
    })
    .UseValidUpdateTypes(UpdateType.Message, UpdateType.EditedMessage, UpdateType.CallbackQuery)
    .UseBotCommands()
    .UseForms())                                    // full form events (optionally pass IExternalActionManager)
```

Available steps: `Use(...)`, `UseValidUpdateTypes(params UpdateType[])`, `UseBotCommands()`, `UseForms(mgr?)`,
`UsePreLoad()`, `UseLoad()`, `UseAttachments(params MessageType[])`, `UseAllAttachments()`, `UseActions()`,
`UseRender()`, `UseActionManager(mgr)`.

Inline-query example (needs `UpdateType.InlineQuery` so the polling subscription includes it):

```csharp
.MiddlewareMessageLoop(ml => ml
    .UseValidUpdateTypes(UpdateType.InlineQuery)
    .Use(async (c, next) => { var q = c.UpdateResult.RawData.InlineQuery.Query; /* … */ await next(); }))
```

### Custom loop

```csharp
public class MyLoop : IMessageLoopFactory
{
    public UpdateType[] ConfigureUpdateTypes() => new[] { UpdateType.Message, UpdateType.CallbackQuery };
    public Task MessageLoop(BotBase bot, IDeviceSession session, UpdateResult ur, MessageResult mr)
        => session.ActiveForm.Load(mr);
}
```

---

## 15. Threading and rate limiting

```csharp
.UseSingleThread()      // sequential, order preserved — default, safest
.UseThreadPool()        // concurrent updates; forms must be thread-safe, order not guaranteed
.UseThreadPool(20, 10)  // worker / IO threads
```

```csharp
.UseDefaultRequestDispatcher()   // concurrency cap + auto retry on HTTP 429
.UseFullRequestDispatcher(new RequestDispatcherSettings
{
    MaxConcurrentRequests = 20, MaxRetryAttempts = 5, RespectRetryAfterHeader = true,
    GlobalPauseOn429 = true,
    MaxRequestsPerSecond = 30, MaxRequestsPerSecondPerChat = 1, MaxRequestsPerMinutePerGroup = 20,
    ChatLimiterCacheTimeout = TimeSpan.FromMinutes(5), GroupLimiterCacheTimeout = TimeSpan.FromMinutes(10)
})
.UseDirectDispatcher()           // no throttling at all
.UseCustomRequestDispatcher(c => new LoggingRequestDispatcher(new FullRequestDispatcher(new(), c)));
```

Custom dispatcher = implement `IRequestDispatcher` (`Dispatch(ds, Func<ITelegramBotClient,Task>, ct)` and the generic
`<T>` overload) and wrap a built-in one.

**Performance rules:** `async` all the way down; never `.Result`/`.Wait()`/`Thread.Sleep` inside a form; offload CPU
work with `Task.Run`; with `UseThreadPool` avoid shared mutable state (or lock it).

---

## 16. Pushing updates without user interaction

```csharp
var timer = new Timer(5000);
timer.Elapsed += async (s, e) =>
{
    foreach (var kv in bot.Sessions.SessionList)
    {
        if (kv.Value.ActiveForm.GetType() != typeof(LiveStatusForm)) continue;
        await bot.InvokeMessageLoop(kv.Key);            // re-runs the full loop for that chat
    }
};
```

`bot.InvokeMessageLoop(deviceId)` or `bot.InvokeMessageLoop(deviceId, customMessageResult)`.
Inside the form, `Render` runs again — edit your tracked message instead of sending a new one.
(See `Examples/AsyncFormUpdates`.)

---

## 17. Hosting

**Console:**

```csharp
await bot.Start();
Console.ReadLine();
await bot.Stop();
```

**ASP.NET Core / Worker Service** (`Examples/BotAndWebApplication`):

```csharp
public class BotBackgroundTask : IHostedService
{
    public BotBase BotBaseInstance { get; }
    public BotBackgroundTask(ILogger<BotBackgroundTask> log) { Logger = log; BotBaseInstance = Build(); }

    public async Task StartAsync(CancellationToken ct)
    {
        await BotBaseInstance.UploadBotCommands();
        await BotBaseInstance.Start();
    }
    public async Task StopAsync(CancellationToken ct)
    {
        await BotBaseInstance.SentToAll("Bot shutting down.");
        await BotBaseInstance.Stop();
    }
}

builder.Services.AddHostedService<BotBackgroundTask>();
```

---

## 18. Extensions packages

| Package | Adds |
|---|---|
| `TelegramBotBase.Extensions.Images` | `Device.SendPhoto(Image\|Bitmap, name, …)`, `image.ToStream(format)` (`System.Drawing.Common`, Windows-only on .NET 6+) |
| `TelegramBotBase.Extensions.Images.IronSoftware` | same via IronSoftware drawing (third-party licence!) |
| `TelegramBotBase.Extensions.ActionManager` | `ExternalActionManager` — global handlers for unhandled callback values |
| `TelegramBotBase.Extensions.Serializer.Database.MSSQL` / `.PostgreSql` | DB-backed `IStateMachine` |
| `TelegramBotBase.Extensions.Serializer.Legacy.NewtonsoftJson` | `UseNewtonsoftJson(...)` state machine |

**ActionManager** — handle callbacks from messages the bot sent *outside* any form (notifications, broadcasts):

```csharp
using TelegramBotBase.Extensions.ActionManager;
using TelegramBotBase.Extensions.ActionManager.Actions;

var eam = ExternalActionManager.Configure(a =>
{
    a.AddInt32Action("test",  async (value, cd, ur, mr) => await mr.Device.Send($"int {value}"));
    a.AddGuidAction ("test2", async (value, cd, ur, mr) => await mr.Device.Send($"guid {value}"));
    a.AddStartsWithAction("test3", async (value, ur, mr) => await mr.Device.Send($"starts {value}"));
});

// wire it in:
.DefaultMessageLoop(eam)          // or FullMessageLoop(eam) / middleware .UseForms(eam)

// and build the buttons with matching serialized CallbackData:
var bf = new ButtonForm();
bf.AddButtonRow(new ButtonBase("1. Test", Int32Action.GetCallback("test", 123)));
bf.AddButtonRow(new ButtonBase("2. Test", GuidAction.GetCallback("test2", Guid.NewGuid())));
bf.AddButtonRow(new ButtonBase("3. Test", "test3"));
```

Action kinds: `AddStringAction`, `AddInt32Action`, `AddInt64Action`, `AddGuidAction` (all
`(value, CallbackData, UpdateResult, MessageResult)`), plus `AddStartsWithAction` / `AddEndsWithAction`
(`(string, UpdateResult, MessageResult)`).

**Navigation actions** — open a form directly from such a callback and inject the value into it:

```csharp
var eam = ExternalActionManager.Configure(a =>
{
    a.AddInt32Navigation<OrderForm>("order", f => f.OrderId);            // sets property, navigates
    a.AddGuidNavigation<TicketForm>("ticket", (f, id) => f.TicketId = id);
    a.AddStartsWithNavigation<SearchForm>("q_", f => f.Query);
});
// Button: new ButtonBase("Open order", Int32Action.GetCallback("order", 42))
```

Variants: `AddStringNavigation`, `AddInt32Navigation`, `AddInt64Navigation`, `AddGuidNavigation`,
`AddStartsWithNavigation`, `AddEndsWithNavigation` (generic `<TForm>` or `Type` overloads).

---

## 19. Text formatting helpers

`TelegramBotBase.Markdown.Generator` (static, `OutputMode` switchable between Markdown and Html):

```csharp
using TelegramBotBase.Markdown;

$"{("Title".Bold())}\n{("sub".Italic())}\n{("no".Strikesthrough())}\n"
"https://example.com".Link("Example", "tooltip")
userId.MentionUser("John")
text.MarkdownV2Escape();       // automatic when parseMode == MarkdownV2 unless markdownV2AutoEscape:false
```

---

## 20. Localizations

`UseEnglish/German/Persian/Russian/Ukrainian/Belarusian/Custom(Localization)` controls the labels of built-in
controls (ButtonGrid paging/search labels, PromptDialog back button, …).

```csharp
public class Italian : Localization
{
    public Italian()
    {
        Values = new()
        {
            ["ButtonGrid_Title"]      = "Menu",
            ["ButtonGrid_NextPage"]   = "Avanti",
            ["ButtonGrid_PreviousPage"]="Indietro",
            ["ButtonGrid_SearchFeature"] = "Cerca",
            ["ButtonGrid_CurrentPage"]   = "Pagina",
            ["ButtonGrid_NoItems"]       = "Nessun elemento",
            ["PromptDialog_Back"]        = "Annulla",
        };
    }
}
// .Custom(new Italian())   — or set Default.Language directly
```

---

## 21. Recommended project layout

```
MyBot/
├─ Program.cs                 builder + bot events + lifetime
├─ Config.cs                  config load/save (never commit secrets)
├─ Forms/
│  ├─ Start.cs                SplitterForm: routes private/group/channel
│  ├─ Menu.cs                 AutoCleanForm main menu
│  └─ …
├─ Controls/                  custom ControlBase subclasses
├─ Services/                  your domain services (registered in DI)
└─ Data/                      EF Core DbContext / repositories
```

---

## 22. Checklist before shipping

- [ ] API key from env var / user secrets / config — **not** source.
- [ ] `await bot.Start()` is awaited and the process stays alive (`ReadLine`, `Task.Delay(-1)`, or `IHostedService`).
- [ ] `await bot.Stop()` on shutdown (saves session states).
- [ ] Every `Action` handler answers the callback: `await message.ConfirmAction()`.
- [ ] `message.Handled = true` set when an action is consumed; guard `if (message.Handled) return;` at the top.
- [ ] Callback data ≤ 64 bytes; message text ≤ 4096 (split or truncate).
- [ ] Controls created in `Init`, added with `AddControl` (not `Controls.Add`).
- [ ] Navigation from a modal dialog avoided (`OpenModal` + `CloseForm`, or navigate from the dialog itself).
- [ ] Forms that must survive restarts have a parameterless ctor and `[SaveState]` fields (or `fallbackForm` set).
- [ ] DI forms navigated with `NavigateTo<T>()` from `TelegramBotBase.DependencyInjection`.
- [ ] `UseThreadPool` only if handlers are thread-safe; otherwise `UseSingleThread`.
- [ ] `bot.Exception` and `bot.UnhandledCall` handlers wired for observability.
- [ ] Logging wired to a middleware step / custom message loop — `bot.Message` and `ESettings.LogAllMessages` are dead, see §11.

---

## 23. Gotchas / FAQ

| Symptom | Cause & fix |
|---|---|
| Button spins forever | Missing `await message.ConfirmAction()`. |
| Menu re-renders after a click | You didn't set `message.Handled = true`, so `Render` ran. |
| `InvalidOperationException: Cannot navigate … from a modal dialog` | `NavigateTo` called inside a `ModalDialog`. Use `CloseForm()` first, or navigate from the parent. |
| Reply-keyboard button does nothing in `Action` | Reply keyboards send *text* — handle in `Load` via `message.Command`. |
| `CallbackDataTooLongException` | Serialized `CallbackData` > 64 bytes. Shorten `Method`/`Value`, store the payload server-side and pass an id. |
| `MessageTooLongException` | > 4096 chars. Split into multiple messages. |
| State not restored after restart | Form lacks `[SaveState]` fields / parameterless ctor / `[IgnoreState]` present / no state machine configured. |
| `InvalidServiceProviderConfiguration` | DI can't construct the form — register the missing service; use `WithServiceProvider<T>` and `NavigateTo<T>()`. |
| Update never reaches my loop | The loop's `ConfigureUpdateTypes()` doesn't include that `UpdateType` (threading stage copies it into `AllowedUpdates`). |
| `FormBase` not found | It's in namespace `TelegramBotBase.Form` (the README's `TelegramBotBase.Base` note is outdated). Controls live in `TelegramBotBase.Controls.Inline` / `.Hybrid`. |
| Navigation chain stops | Max 10 chained navigations per update (`ESettings.NavigationMaximum`). |
| `bot.Message` / `Device.MessageReceived` never fires | Both are declared but never raised by the library. Use a middleware step or custom message loop for inbound logging (§11). |

---

## 24. Where to look in the source

| Need | File |
|---|---|
| Builder API | `TelegramBotBase/Builder/BotBaseBuilder.cs` (+ `Builder/Interfaces/*`) |
| Bot root, events, settings | `TelegramBotBase/BotBase.cs`, `SessionManager.cs` |
| Form lifecycle | `TelegramBotBase/Base/FormBase.cs`, `Form/AutoCleanForm.cs` |
| Message loop default | `TelegramBotBase/MessageLoops/FormBaseMessageLoop.cs`, `MinimalMessageLoop.cs`, `FullMessageLoop.cs`, `MiddlewareBaseMessageLoop.cs`, `Extensions/MiddlewareBaseMessageLoopExtensions.cs` |
| Chat/session API | `TelegramBotBase/Sessions/DeviceSession.cs`, `Interfaces/IDeviceSession.cs`, `Interfaces/IDeviceSessionMethods.cs` |
| Buttons | `Form/ButtonForm.cs`, `Form/ButtonBase.cs`, `Form/DynamicButton.cs`, `Form/TagButtonBase.cs`, `Form/WebAppButtonBase.cs`, `Form/CallbackData.cs`, `Controls/Hybrid/ButtonGrid.cs` |
| Data sources | `TelegramBotBase/DataSources/*`, `TelegramBotBase.Test/Tests/DataSources/*` |
| ActionManager | `TelegramBotBase.Extensions.ActionManager/Actions/*`, `Navigation/*` |
| Dialogs | `Form/ModalDialog.cs`, `PromptDialog.cs`, `ConfirmDialog.cs`, `AlertDialog.cs`, `ArrayPromptDialog.cs` |
| Navigation | `Form/Navigation/NavigationController.cs`, `DependencyInjection/Extensions.cs` |
| DI | `Factories/ServiceProviderFormFactory.cs`, `DependencyInjection/FormDiEscort.cs` |
| State | `States/JSONStateMachine.cs`, `SimpleJSONStateMachine.cs`, `XMLStateMachine.cs`, `Attributes/*` |
| Dispatchers | `TelegramBotBase/RequestDispatchers/*` |
| Groups | `Form/SplitterForm.cs`, `Form/GroupForm.cs` |
| Limits | `TelegramBotBase/Constants/Telegram.cs` |
| Markdown | `TelegramBotBase/Markdown/Generator.cs` |
| Worked examples | `Examples/*` (SystemCommandsBot, JoinHiderBot, DependencyInjection, EFCoreBot, AsyncFormUpdates, BotAndWebApplication, InlineAndReplyCombination, MiddlewareBaseBot, ModalDialogNavigation, FileWatcher) and `TelegramBotBase.Test/Tests/**` (one form per control) |