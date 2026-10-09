import QtQuick

// TrainzUtil installer. Same glass as the other studios: raised plates, sunk wells.
Item {
    id: root
    property bool sideOpen: true
    property bool taskOpen: true
    property bool depsOpen: true
    readonly property real sideWide: Math.min(420, Math.max(300, (stage.width - 160) * 0.26))
    readonly property real taskWide: Math.min(380, Math.max(280, (stage.width - 160) * 0.22))
    property real sideLayout: sideWide
    property real sideVisual: sideWide
    property real taskLayout: taskWide
    property real taskVisual: taskWide
    property real sideWant: 0
    property real taskWant: 0
    property bool sideDrag: false
    property bool taskDrag: false

    function fitSide(w) {
        var other = taskOpen ? taskVisual : 72
        var cap = Math.max(260, stage.width - other - 220)
        return Math.max(260, Math.min(720, Math.min(w, cap)))
    }

    function fitTask(w) {
        var other = sideOpen ? sideVisual : 72
        var cap = Math.max(240, stage.width - other - 220)
        return Math.max(240, Math.min(640, Math.min(w, cap)))
    }

    function syncPanes() {
        if (sideAnim.running || taskAnim.running || sideDrag || taskDrag)
            return
        if (sideOpen) {
            var w = sideWant > 0 ? fitSide(sideWant) : sideWide
            sideLayout = w
            sideVisual = w
        }
        if (taskOpen) {
            var t = taskWant > 0 ? fitTask(taskWant) : taskWide
            taskLayout = t
            taskVisual = t
        }
        if (sideOpen) {
            var w2 = sideWant > 0 ? fitSide(sideWant) : Math.min(sideWide, fitSide(sideWide))
            sideLayout = w2
            sideVisual = w2
        }
    }

    function openDependency(kuid) {
        var index = bridge.rowIndex(kuid)
        if (index < 0 && bridge.libraryHas(kuid)) {
            findInput.text = ""
            bridge.filterLibrary("")
            index = bridge.rowIndex(kuid)
        }
        if (index >= 0)
            libraryList.positionViewAtIndex(index, ListView.Contain)
        bridge.focusAsset(kuid)
    }

    function setSideOpen(open) {
        if (open === sideOpen && !sideAnim.running)
            return
        sideOpen = open
        var sideDest = open ? (sideWant > 0 ? fitSide(sideWant) : sideWide) : 72
        sideAnim.from = sideVisual
        sideAnim.to = sideDest
        if (open)
            sideLayout = sideDest
        sideAnim.start()
    }

    function setTaskOpen(open) {
        if (open === taskOpen && !taskAnim.running)
            return
        taskOpen = open
        var taskDest = open ? (taskWant > 0 ? fitTask(taskWant) : taskWide) : 72
        taskAnim.from = taskVisual
        taskAnim.to = taskDest
        if (open)
            taskLayout = taskDest
        taskAnim.start()
    }

    NumberAnimation {
        id: sideAnim
        target: root
        property: "sideVisual"
        duration: 180
        easing.type: Easing.OutCubic
        onStopped: if (!root.sideOpen) root.sideLayout = 72
    }
    NumberAnimation {
        id: taskAnim
        target: root
        property: "taskVisual"
        duration: 180
        easing.type: Easing.OutCubic
        onStopped: if (!root.taskOpen) root.taskLayout = 72
    }

    component ColHead: Item {
        id: col
        property string title: ""
        property string key: ""
        property string field: ""
        width: col.span()
        height: 22

        function span() {
            if (field === "name")
                return mid.nameW
            if (field === "status")
                return mid.statW
            if (field === "modified")
                return mid.modifiedW
            if (field === "size")
                return mid.sizeW
            if (field === "kuid")
                return mid.kuidW
            if (field === "author")
                return mid.authorW
            if (field === "build")
                return mid.buildW
            return mid.catW
        }

        function setSpan(value) {
            var next = Math.max(64, value)
            if (field === "name")
                mid.nameW = next
            else if (field === "status")
                mid.statW = next
            else if (field === "modified")
                mid.modifiedW = next
            else if (field === "size")
                mid.sizeW = next
            else if (field === "kuid")
                mid.kuidW = next
            else if (field === "author")
                mid.authorW = next
            else if (field === "build")
                mid.buildW = next
            else
                mid.catW = next
        }

        Text {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.rightMargin: 8
            anchors.verticalCenter: parent.verticalCenter
            text: title + (bridge.sortMark === key ? " ▲" : (bridge.sortMark === key + ":desc" ? " ▼" : ""))
            color: (bridge.sortMark === key || bridge.sortMark === key + ":desc") ? "#ff5a1f" : "#9aa3b2"
            font.pixelSize: 11
            font.bold: true
            elide: Text.ElideRight
            TapHandler { onTapped: bridge.sortLibrary(key) }
        }
        Rectangle {
            width: 1
            height: 12
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            color: Qt.rgba(1, 1, 1, 0.22)
        }
        MouseArea {
            anchors.right: parent.right
            anchors.rightMargin: -3
            anchors.verticalCenter: parent.verticalCenter
            width: 8
            height: parent.height
            cursorShape: Qt.SplitHCursor
            preventStealing: true
            property real originX: 0
            property real originW: 0
            onPressed: function (mouse) { originX = mouse.x; originW = col.width }
            onPositionChanged: function (mouse) {
                if (pressed)
                    col.setSpan(originW + mouse.x - originX)
            }
        }
    }

    ListModel { id: contentModel }
    ListModel { id: sourceModel }
    ListModel { id: scriptModel }
    ListModel { id: logModel }
    ListModel { id: backupModel }
    ListModel { id: taskModel }

    function statusFill(name) {
        if (name === "Faulty" || name === "Missing")
            return Qt.rgba(1, 0.35, 0.12, bridge.dark ? 0.38 : 0.18)
        if (name === "Edit" || name === "Installed")
            return Qt.rgba(0.24, 0.86, 0.52, bridge.dark ? 0.22 : 0.18)
        if (name === "Modified" || name === "Update")
            return Qt.rgba(0.95, 0.72, 0.25, bridge.dark ? 0.28 : 0.22)
        return Qt.rgba(1, 1, 1, bridge.dark ? 0.08 : 0.4)
    }

    function statusInk(name) {
        if (name === "Faulty" || name === "Missing")
            return bridge.dark ? "#ffb199" : "#9a3412"
        if (name === "Edit" || name === "Installed")
            return bridge.dark ? "#b6f5cf" : "#166534"
        if (name === "Modified" || name === "Update")
            return bridge.dark ? "#ffe2a8" : "#854d0e"
        return bridge.dark ? "#f2f4f8" : "#1d1d1f"
    }

    component StatusChip: Rectangle {
        property string label: ""
        radius: 11
        implicitHeight: 22
        implicitWidth: chipText.implicitWidth + 16
        color: root.statusFill(label)
        Text {
            id: chipText
            anchors.centerIn: parent
            text: label
            color: root.statusInk(label)
            font.pixelSize: 11
            font.bold: true
        }
    }

    component StatTile: Item {
        property string cap: ""
        property string val: ""
        implicitHeight: 58
        Rectangle {
            anchors.fill: parent
            radius: 12
            color: Qt.rgba(0, 0, 0, bridge.dark ? 0.42 : 0.12)
            border.width: 1
            border.color: Qt.rgba(0, 0, 0, bridge.dark ? 0.55 : 0.16)
            Rectangle {
                anchors.top: parent.top
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.margins: 1
                height: 14
                radius: 11
                gradient: Gradient {
                    GradientStop { position: 0.0; color: Qt.rgba(0, 0, 0, bridge.dark ? 0.45 : 0.16) }
                    GradientStop { position: 1.0; color: Qt.rgba(0, 0, 0, 0) }
                }
            }
            Rectangle {
                anchors.bottom: parent.bottom
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.leftMargin: 8
                anchors.rightMargin: 8
                height: 1
                color: Qt.rgba(1, 1, 1, bridge.dark ? 0.10 : 0.55)
            }
        }
        Column {
            anchors.fill: parent
            anchors.leftMargin: 10
            anchors.rightMargin: 10
            anchors.topMargin: 8
            spacing: 3
            Text {
                text: cap
                color: bridge.dark ? "#8b93a1" : "#5c6570"
                font.pixelSize: 10
                font.bold: true
                font.capitalization: Font.AllUppercase
            }
            Text {
                width: parent.width
                text: val.length ? val : "—"
                color: bridge.dark ? "#f2f4f8" : "#1d1d1f"
                font.pixelSize: 13
                font.bold: true
                elide: Text.ElideRight
            }
        }
    }

    function collectChecked() {
        var ids = []
        for (var i = 0; i < contentModel.count; ++i) {
            var row = contentModel.get(i)
            if (row.checked && row.canInstall)
                ids.push(row.jobId)
        }
        return ids
    }

    function setAll(on) {
        for (var i = 0; i < contentModel.count; ++i) {
            if (contentModel.get(i).canInstall)
                contentModel.setProperty(i, "checked", on)
        }
    }

    readonly property bool sheetOn: taskLogOn || logDialog.logShown || (bridge.loadOn && bridge.libraryOn)
    property string taskOpenId: ""
    property bool taskLogOn: false
    onTaskLogOnChanged: logDialog.syncLog()
    property string taskLogTitle: ""
    property string taskLogAction: ""
    property string taskLogBody: ""
    onTaskLogBodyChanged: {
        logSel = ({})
        logAnchor = -1
        logTone = ""
    }
    property string logTone: ""
    readonly property var logRows: bridge.classifyLog(taskLogBody)
    readonly property var logView: {
        var tone = logTone
        var rows = logRows
        var out = []
        if (!rows)
            return out
        for (var i = 0; i < rows.length; ++i) {
            if (tone && rows[i].tone !== tone)
                continue
            out.push({ src: i, text: rows[i].text, tone: rows[i].tone })
        }
        return out
    }

    function toneColor(tone) {
        if (tone === "error")
            return bridge.dark ? "#ffd0cc" : "#9f1c1c"
        if (tone === "warn")
            return bridge.dark ? "#ffe7a3" : "#7a5b00"
        if (tone === "ok")
            return bridge.dark ? "#b6f5d0" : "#0d7a45"
        return bridge.dark ? "#d5dbe3" : "#1d1d1f"
    }

    function toneFill(tone) {
        if (tone === "error")
            return bridge.dark ? Qt.rgba(0.62, 0.12, 0.14, 0.72) : Qt.rgba(0.86, 0.22, 0.22, 0.22)
        if (tone === "warn")
            return bridge.dark ? Qt.rgba(0.55, 0.38, 0.08, 0.72) : Qt.rgba(0.86, 0.62, 0.08, 0.28)
        if (tone === "ok")
            return bridge.dark ? Qt.rgba(0.08, 0.38, 0.20, 0.72) : Qt.rgba(0.10, 0.55, 0.32, 0.18)
        return bridge.dark ? Qt.rgba(1, 1, 1, 0.05) : Qt.rgba(1, 1, 1, 0.55)
    }

    function toneCount(tone) {
        var n = 0
        for (var i = 0; i < logRows.length; ++i) {
            if (logRows[i].tone === tone)
                n++
        }
        return n
    }

    property var logSel: ({})
    property int logAnchor: -1
    property int srcAnchor: -1
    property int fileAnchor: -1
    property int scriptAnchor: -1
    property int backupAnchor: -1
    property int taskAnchor: -1
    property var scriptBag: ({})
    property var backupBag: ({})
    property var taskBag: ({})
    FontMetrics {
        id: logFont
        font.family: "Consolas"
        font.pixelSize: 10
    }
    readonly property real logMaxW: {
        var w = 40
        var rows = logRows
        if (!rows)
            return w
        for (var i = 0; i < rows.length; ++i)
            w = Math.max(w, logFont.advanceWidth(String(rows[i].text)) + 36)
        return w
    }

    function logOn(index) {
        return !!logSel[String(index)]
    }

    function logSelCount() {
        return Object.keys(logSel).length
    }

    function modBits(mods) {
        if (mods === undefined || mods === null)
            return 0
        if (typeof mods === "number")
            return mods
        if (mods.value !== undefined)
            return mods.value
        return Number(mods) || 0
    }

    function modOn(mods, flag) {
        var bit = modBits(flag)
        return bit !== 0 && (modBits(mods) & bit) === bit
    }

    function logClick(index, modifiers) {
        var shift = modOn(modifiers, Qt.ShiftModifier)
        var ctrl = modOn(modifiers, Qt.ControlModifier)
        var view = logView
        var next = {}
        function posOf(src) {
            for (var i = 0; i < view.length; ++i) {
                if (view[i].src === src)
                    return i
            }
            return -1
        }
        var anchor = logAnchor
        if (shift) {
            if (ctrl) {
                for (var k in logSel)
                    next[k] = true
            }
            var pa = posOf(anchor)
            var pb = posOf(index)
            if (pa < 0)
                pa = pb
            if (pb < 0)
                return
            var a = Math.min(pa, pb)
            var b = Math.max(pa, pb)
            for (var i = a; i <= b; ++i)
                next[String(view[i].src)] = true
            logSel = next
            return
        }
        logAnchor = index
        if (ctrl) {
            for (var c in logSel)
                next[c] = true
            var key = String(index)
            if (next[key])
                delete next[key]
            else
                next[key] = true
            logSel = next
            return
        }
        next[String(index)] = true
        logSel = next
    }

    function logSelectAll() {
        var next = {}
        var view = logView
        for (var i = 0; i < view.length; ++i)
            next[String(view[i].src)] = true
        logAnchor = view.length ? view[0].src : -1
        logSel = next
    }

    function toggleLogTone(tone) {
        logTone = logTone === tone ? "" : tone
        logSel = ({})
        logAnchor = -1
    }

    function logLines(tone) {
        var out = []
        for (var i = 0; i < logRows.length; ++i) {
            if (!tone || logRows[i].tone === tone)
                out.push(logRows[i].text)
        }
        return out.join("\n")
    }

    function logSelectedText() {
        var keys = Object.keys(logSel).map(function (k) { return Number(k) })
        keys.sort(function (a, b) { return a - b })
        var out = []
        for (var i = 0; i < keys.length; ++i) {
            var row = logRows[keys[i]]
            if (row)
                out.push(row.text)
        }
        return out.join("\n")
    }

    function rangeCheck(model, index, modifiers, anchorName, gate) {
        var shift = (modifiers & Qt.ShiftModifier) !== 0
        var ctrl = (modifiers & Qt.ControlModifier) !== 0
        function allowed(i) {
            if (!gate)
                return true
            return !!model.get(i)[gate]
        }
        var anchor = root[anchorName]
        if (anchor < 0 || anchor >= model.count)
            anchor = index
        if (shift) {
            var a = Math.min(anchor, index)
            var b = Math.max(anchor, index)
            for (var i = 0; i < model.count; ++i) {
                if (!allowed(i))
                    continue
                var on = (i >= a && i <= b)
                if (ctrl)
                    on = model.get(i).checked || on
                if (model.get(i).checked !== on)
                    model.setProperty(i, "checked", on)
            }
            return
        }
        root[anchorName] = index
        if (!allowed(index))
            return
        if (ctrl) {
            model.setProperty(index, "checked", !model.get(index).checked)
            return
        }
        for (var k = 0; k < model.count; ++k) {
            if (!allowed(k))
                continue
            var want = k === index
            if (model.get(k).checked !== want)
                model.setProperty(k, "checked", want)
        }
    }

    function idsOf(model, role) {
        var ids = []
        for (var i = 0; i < model.count; ++i)
            ids.push(String(model.get(i)[role]))
        return ids
    }

    function bagOn(bag, id) {
        return !!bag[String(id)]
    }

    function rangeBag(ids, index, modifiers, anchorName, bagName) {
        var shift = (modifiers & Qt.ShiftModifier) !== 0
        var ctrl = (modifiers & Qt.ControlModifier) !== 0
        var anchor = root[anchorName]
        if (anchor < 0 || anchor >= ids.length)
            anchor = index
        var next = {}
        if (shift) {
            if (ctrl) {
                var prev = root[bagName]
                for (var p in prev)
                    next[p] = true
            }
            var a = Math.min(anchor, index)
            var b = Math.max(anchor, index)
            for (var i = a; i <= b; ++i)
                next[ids[i]] = true
            root[bagName] = next
            return
        }
        root[anchorName] = index
        if (ctrl) {
            var cur = root[bagName]
            for (var c in cur)
                next[c] = true
            if (next[ids[index]])
                delete next[ids[index]]
            else
                next[ids[index]] = true
            root[bagName] = next
            return
        }
        next[ids[index]] = true
        root[bagName] = next
    }

    function openTaskLog(taskId) {
        for (var i = 0; i < taskModel.count; ++i) {
            var row = taskModel.get(i)
            if (row.taskId !== taskId)
                continue
            taskOpenId = taskId
            taskLogTitle = row.name
            taskLogAction = row.action + "  ·  " + row.phase
            taskLogBody = row.log || row.detail || "No log yet."
            taskLogOn = true
            return
        }
    }

    property string backupKind: "Folder"
    property string backupOrder: "new"
    property var backupAll: []
    onBackupKindChanged: applyBackupView()
    onBackupOrderChanged: applyBackupView()

    function applyBackupView() {
        var rows = []
        for (var i = 0; i < backupAll.length; ++i) {
            if (backupAll[i].kind === backupKind)
                rows.push(backupAll[i])
        }
        var dir = backupOrder === "new" ? -1 : 1
        rows.sort(function (a, b) {
            if (a.dayKey < b.dayKey)
                return -dir
            if (a.dayKey > b.dayKey)
                return dir
            if (a.mtime < b.mtime)
                return -dir
            if (a.mtime > b.mtime)
                return dir
            return 0
        })
        backupModel.clear()
        for (var j = 0; j < rows.length; ++j) {
            var row = rows[j]
            backupModel.append({
                day: row.day,
                title: row.title,
                kind: row.kind,
                detail: row.detail,
                path: row.path
            })
        }
    }

    function markJob(id, state) {
        for (var i = 0; i < contentModel.count; ++i) {
            if (contentModel.get(i).jobId === id)
                contentModel.setProperty(i, "state", state)
        }
    }

    Connections {
        target: bridge
        function onContentsReady(rows) {
            contentModel.clear()
            for (var i = 0; i < rows.length; ++i) {
                var row = rows[i]
                contentModel.append({
                    jobId: row.jobId,
                    label: row.label,
                    kind: row.kind,
                    detail: row.detail,
                    canInstall: row.canInstall,
                    checked: row.checked,
                    openable: row.openable,
                    state: ""
                })
            }
        }
        function onSourcesReady(rows) {
            sourceModel.clear()
            for (var i = 0; i < rows.length; ++i) {
                var row = rows[i]
                sourceModel.append({
                    sourceId: row.sourceId,
                    name: row.name,
                    kind: row.kind,
                    size: row.size,
                    status: row.status,
                    percent: row.percent || 0,
                    checked: !!row.checked
                })
            }
        }
        function onScriptsReady(rows) {
            scriptModel.clear()
            for (var i = 0; i < rows.length; ++i) {
                var row = rows[i]
                scriptModel.append({
                    scriptId: row.scriptId,
                    name: row.name,
                    folder: row.folder,
                    status: row.status,
                    tone: row.tone
                })
            }
        }
        function onLogLine(text) {
            logModel.insert(0, { line: text })
            if (logModel.count > 80)
                logModel.remove(80)
        }
        function onJobState(id, state) {
            markJob(id, state)
        }
        function onBackupsReady(rows) {
            backupAll = rows
            applyBackupView()
        }
        function onTasksReady(rows) {
            var open = taskOpenId
            var still = false
            taskModel.clear()
            for (var i = 0; i < rows.length; ++i) {
                var row = rows[i]
                taskModel.append({
                    taskId: row.taskId || "",
                    name: row.name,
                    action: row.action,
                    phase: row.state,
                    detail: row.detail || "",
                    log: row.log || "",
                    percent: row.percent
                })
                if (open && row.taskId === open) {
                    still = true
                    taskLogTitle = row.name
                    taskLogAction = row.action + "  ·  " + row.state
                    taskLogBody = row.log || row.detail || ""
                }
            }
            if (open && !still)
                taskLogOn = false
        }
    }

    Chrome { id: chrome }

    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            GradientStop { position: 0.0; color: bridge.dark ? "#1a2230" : "#eef1f6" }
            GradientStop { position: 1.0; color: bridge.dark ? "#0c0e12" : "#d5dbe3" }
        }
    }

    Item {
        id: stage
        enabled: !root.sheetOn
        anchors.fill: parent
        anchors.leftMargin: 10
        anchors.rightMargin: 10
        anchors.topMargin: 8
        anchors.bottomMargin: chrome.stageMargin
        onWidthChanged: root.syncPanes()

        GlassPlate {
            id: side
            anchors.left: parent.left
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            width: root.sideVisual
            clip: true
            dark: bridge.dark
            plateRadius: 16
            foot: 8
            readonly property color ink: bridge.dark ? "#f2f4f8" : "#1d1d1f"
            readonly property color mute: bridge.dark ? "#8b93a1" : "#5c6570"

            RaiseButton {
                z: 3
                width: 32
                height: 32
                y: 0
                x: root.sideOpen ? parent.width - width : (parent.width - width) / 2
                glyph: root.sideOpen ? bridge.glyphChevronLeft : bridge.glyphChevronRight
                fontName: bridge.iconFont
                tip: root.sideOpen ? "Collapse" : "Expand"
                onClicked: root.setSideOpen(!root.sideOpen)
            }

            DropArea {
                anchors.fill: parent
                onDropped: function (drop) {
                    var urls = []
                    for (var i = 0; i < drop.urls.length; ++i)
                        urls.push(String(drop.urls[i]))
                    bridge.dropUrls(urls)
                    drop.acceptProposedAction()
                }
            }

            Column {
                id: sideHead
                visible: root.sideOpen && !sideAnim.running
                anchors.top: parent.top
                anchors.left: parent.left
                anchors.right: parent.right
                spacing: 8
                Image {
                    anchors.horizontalCenter: parent.horizontalCenter
                    width: 108
                    height: 36
                    fillMode: Image.PreserveAspectFit
                    source: bridge.dark ? "image://mstnlogo/dark" : "image://mstnlogo/light"
                }
                Text {
                    width: parent.width
                    horizontalAlignment: Text.AlignHCenter
                    text: "Smart TrainzUtil"
                    color: side.ink
                    font.pixelSize: 15
                    font.bold: true
                }
                Row {
                    anchors.horizontalCenter: parent.horizontalCenter
                    spacing: 8
                    Rectangle {
                        width: 8
                        height: 8
                        radius: 4
                        anchors.verticalCenter: parent.verticalCenter
                        color: bridge.launcherOk ? "#3ddc84" : "#ff5a1f"
                    }
                    Text {
                        text: bridge.launcherText
                        color: side.ink
                        font.pixelSize: 12
                        font.bold: true
                    }
                }
                Row {
                    anchors.horizontalCenter: parent.horizontalCenter
                    spacing: 8
                    RaiseButton {
                        width: 108
                        height: 36
                        glyph: bridge.glyphFolder
                        fontName: bridge.iconFont
                        label: "Data"
                        accent: true
                        tip: "Open the Trainz data folder"
                        onClicked: bridge.browseData()
                    }
                    RaiseButton {
                        visible: bridge.utilPath.indexOf("not found") >= 0
                        width: 40
                        height: 36
                        glyph: bridge.glyphFolder
                        fontName: bridge.iconFont
                        tip: "Browse TrainzUtil.exe"
                        onClicked: bridge.browseUtil()
                    }
                    RaiseButton {
                        width: 40
                        height: 36
                        glyph: bridge.glyphRefresh
                        fontName: bridge.iconFont
                        tip: "Refresh"
                        onClicked: bridge.refreshLauncher()
                    }
                    RaiseButton {
                        width: 40
                        height: 36
                        label: "+"
                        tip: bridge.page === "encrypt" ? "Add .gs scripts" : "Add zip or CDP"
                        onClicked: bridge.addFiles()
                    }
                    RaiseButton {
                        width: 40
                        height: 36
                        label: "×"
                        tip: bridge.page === "encrypt" ? "Clear scripts" : "Clear packages"
                        onClicked: bridge.clearSources()
                    }
                }
                Rectangle {
                    width: parent.width
                    height: 1
                    color: Qt.rgba(1, 1, 1, bridge.dark ? 0.08 : 0.35)
                }
            }

            Item {
                id: stack
                visible: root.sideOpen && !sideAnim.running
                anchors.top: sideHead.bottom
                anchors.topMargin: 12
                anchors.bottom: parent.bottom
                anchors.left: parent.left
                anchors.right: parent.right

                GlassPlate {
                    id: detailWell
                    anchors.top: parent.top
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.bottom: parent.bottom
                    sunk: true
                    dark: bridge.dark
                    plateRadius: 14
                    foot: 4

                    Flickable {
                        id: detailFlick
                        anchors.fill: parent
                        contentHeight: detailCol.height
                        clip: true
                        boundsBehavior: Flickable.StopAtBounds

                        Column {
                            id: detailCol
                            width: parent.width
                            spacing: 12

                            Item {
                                width: parent.width
                                height: bridge.detailOn ? 0 : Math.max(160, detailFlick.height)
                                visible: !bridge.detailOn
                                Column {
                                    anchors.centerIn: parent
                                    width: parent.width
                                    spacing: 6
                                    Text {
                                        width: parent.width
                                        horizontalAlignment: Text.AlignHCenter
                                        text: "View detail"
                                        color: side.ink
                                        font.pixelSize: 18
                                        font.bold: true
                                    }
                                    Text {
                                        width: parent.width
                                        horizontalAlignment: Text.AlignHCenter
                                        wrapMode: Text.Wrap
                                        text: "Tick library rows to see each one here. Click a ticked row for its dependencies."
                                        color: side.mute
                                        font.pixelSize: 12
                                    }
                                }
                            }

                                Column {
                                    width: parent.width
                                    visible: bridge.detailOn
                                    spacing: 12

                                    Text {
                                        width: parent.width
                                        visible: bridge.detailCards.length > 1
                                        text: bridge.detailCards.length + " selected"
                                        color: side.mute
                                        font.pixelSize: 11
                                        font.bold: true
                                        font.capitalization: Font.AllUppercase
                                    }

                                    Row {
                                        width: parent.width
                                        spacing: 8
                                        RaiseButton {
                                            width: (parent.width - 32) / 5
                                            height: 36
                                            glyph: bridge.glyphHistory
                                            fontName: bridge.iconFont
                                            accent: true
                                            tip: "Find backups"
                                            onClicked: bridge.findSelectedBackups()
                                        }
                                        RaiseButton {
                                            width: (parent.width - 32) / 5
                                            height: 36
                                            enabled: !bridge.taskBusy
                                            glyph: bridge.glyphEdit
                                            fontName: bridge.iconFont
                                            tip: "Open for editing"
                                            onClicked: bridge.openForEditing()
                                        }
                                        RaiseButton {
                                            width: (parent.width - 32) / 5
                                            height: 36
                                            enabled: !bridge.taskBusy
                                            glyph: bridge.glyphPublish
                                            fontName: bridge.iconFont
                                            tip: "Submit edit"
                                            onClicked: bridge.submitEdit()
                                        }
                                        RaiseButton {
                                            width: (parent.width - 32) / 5
                                            height: 36
                                            enabled: !bridge.taskBusy
                                            glyph: bridge.glyphCheck
                                            fontName: bridge.iconFont
                                            tip: "Validate"
                                            onClicked: bridge.validateAssets()
                                        }
                                        RaiseButton {
                                            width: (parent.width - 32) / 5
                                            height: 36
                                            glyph: bridge.glyphAssets
                                            fontName: bridge.iconFont
                                            tip: "Packages"
                                            onClicked: bridge.openPackages()
                                        }
                                    }

                                    Repeater {
                                        model: bridge.detailCards
                                        delegate: Rectangle {
                                            id: assetCard
                                            required property var modelData
                                            readonly property bool focused: modelData.kuid === bridge.detailKuid
                                            width: detailCol.width
                                            height: cardCol.height + 16
                                            radius: 12
                                            color: bridge.detailCards.length > 1 && focused
                                                   ? Qt.rgba(1, 0.35, 0.12, bridge.dark ? 0.16 : 0.1)
                                                   : Qt.rgba(1, 1, 1, bridge.dark ? 0.04 : 0.4)
                                            border.width: bridge.detailCards.length > 1 && focused ? 1 : 0
                                            border.color: "#ff5a1f"

                                            Column {
                                                id: cardCol
                                                x: 8
                                                y: 8
                                                width: parent.width - 16
                                                spacing: 8

                                                Rectangle {
                                                    width: parent.width
                                                    height: focused ? 168 : 0
                                                    visible: focused
                                                    radius: 12
                                                    clip: true
                                                    color: Qt.rgba(0, 0, 0, bridge.dark ? 0.35 : 0.06)
                                                    Image {
                                                        anchors.fill: parent
                                                        visible: bridge.coverUrl.length > 0
                                            source: bridge.coverUrl
                                            fillMode: Image.PreserveAspectCrop
                                            asynchronous: true
                                            sourceSize.width: 640
                                            sourceSize.height: 360
                                                    }
                                                    Text {
                                                        anchors.centerIn: parent
                                                        width: parent.width - 16
                                                        horizontalAlignment: Text.AlignHCenter
                                                        visible: bridge.coverUrl.length === 0
                                                        text: bridge.coverBusy ? "Loading preview…" : "No preview"
                                                        color: side.mute
                                                        font.pixelSize: 12
                                                    }
                                                }

                                                Text {
                                                    width: parent.width
                                                    text: modelData.category || "Asset"
                                                    color: "#ff7a45"
                                                    font.pixelSize: 11
                                                    font.bold: true
                                                    font.capitalization: Font.AllUppercase
                                                    elide: Text.ElideRight
                                                }
                                                Text {
                                                    width: parent.width
                                                    wrapMode: Text.Wrap
                                                    text: modelData.title || ""
                                                    color: side.ink
                                                    font.pixelSize: focused ? 20 : 15
                                                    font.bold: true
                                                }
                                                Flow {
                                                    width: parent.width
                                                    spacing: 6
                                                    visible: focused && bridge.detailStatus.length > 0
                                                    Repeater {
                                                        model: bridge.detailStatus
                                                        delegate: StatusChip {
                                                            required property string modelData
                                                            label: modelData
                                                        }
                                                    }
                                                }
                                                Text {
                                                    width: parent.width
                                                    visible: !focused && (modelData.statusText || "").length > 0
                                                    text: modelData.statusText || ""
                                                    color: side.mute
                                                    font.pixelSize: 11
                                                    elide: Text.ElideRight
                                                }
                                                Rectangle {
                                                    width: parent.width
                                                    height: 32
                                                    radius: 10
                                                    color: Qt.rgba(0, 0, 0, bridge.dark ? 0.28 : 0.06)
                                                    Text {
                                                        anchors.fill: parent
                                                        anchors.leftMargin: 10
                                                        anchors.rightMargin: 10
                                                        verticalAlignment: Text.AlignVCenter
                                                        text: modelData.kuid || ""
                                                        color: side.ink
                                                        font.pixelSize: 12
                                                        font.family: "Consolas"
                                                        elide: Text.ElideMiddle
                                                    }
                                                }
                                                Grid {
                                                    width: parent.width
                                                    visible: focused
                                                    columns: 2
                                                    columnSpacing: 8
                                                    rowSpacing: 8
                                                    StatTile {
                                                        width: (parent.width - 8) / 2
                                                        cap: "Trainz-build"
                                                        val: modelData.build || ""
                                                    }
                                                    StatTile {
                                                        width: (parent.width - 8) / 2
                                                        cap: "Modified"
                                                        val: modelData.modified || ""
                                                    }
                                                    StatTile {
                                                        width: (parent.width - 8) / 2
                                                        cap: "Size"
                                                        val: modelData.size || ""
                                                    }
                                                    StatTile {
                                                        width: (parent.width - 8) / 2
                                                        cap: "Author"
                                                        val: modelData.author || ""
                                                    }
                                                }
                                                Rectangle {
                                                    readonly property string note: modelData.note || ""
                                                    readonly property bool warn: note.indexOf("Launcher") >= 0 || note.toLowerCase().indexOf("error") >= 0
                                                    width: parent.width
                                                    visible: focused && note.length > 0 && bridge.detailDeps.length === 0
                                                    height: visible ? cardNote.implicitHeight + 16 : 0
                                                    radius: 10
                                                    color: warn
                                                           ? Qt.rgba(1, 0.45, 0.28, bridge.dark ? 0.14 : 0.12)
                                                           : Qt.rgba(1, 1, 1, bridge.dark ? 0.045 : 0.45)
                                                    Text {
                                                        id: cardNote
                                                        anchors.left: parent.left
                                                        anchors.right: parent.right
                                                        anchors.verticalCenter: parent.verticalCenter
                                                        anchors.leftMargin: 10
                                                        anchors.rightMargin: 10
                                                        wrapMode: Text.Wrap
                                                        text: parent.note
                                                        color: side.ink
                                                        font.pixelSize: 12
                                                    }
                                                }
                                                Column {
                                                    id: depBlock
                                                    width: parent.width
                                                    spacing: 8
                                                    visible: focused && bridge.detailDeps.length > 0
                                                    Item {
                                                        width: parent.width
                                                        height: 22
                                                        Row {
                                                            spacing: 8
                                                            anchors.verticalCenter: parent.verticalCenter
                                                            Text {
                                                                text: bridge.glyphChevronRight
                                                                rotation: root.depsOpen ? 90 : 0
                                                                color: side.mute
                                                                font.pixelSize: 16
                                                                font.family: bridge.iconFont
                                                                anchors.verticalCenter: parent.verticalCenter
                                                            }
                                                            Text {
                                                                text: "Dependencies"
                                                                color: side.mute
                                                                font.pixelSize: 11
                                                                font.bold: true
                                                                font.capitalization: Font.AllUppercase
                                                                anchors.verticalCenter: parent.verticalCenter
                                                            }
                                                            Rectangle {
                                                                radius: 8
                                                                height: 16
                                                                width: depCount.implicitWidth + 10
                                                                color: Qt.rgba(1, 0.35, 0.12, bridge.dark ? 0.28 : 0.16)
                                                                anchors.verticalCenter: parent.verticalCenter
                                                                Text {
                                                                    id: depCount
                                                                    anchors.centerIn: parent
                                                                    text: bridge.detailDeps.length
                                                                    color: bridge.dark ? "#ffb199" : "#9a3412"
                                                                    font.pixelSize: 10
                                                                    font.bold: true
                                                                }
                                                            }
                                                        }
                                                        TapHandler { onTapped: root.depsOpen = !root.depsOpen }
                                                    }
                                                    Repeater {
                                                        model: root.depsOpen ? bridge.detailDeps : []
                                                        delegate: Rectangle {
                                                            required property var modelData
                                                            width: cardCol.width
                                                            height: 48
                                                            radius: 12
                                                            color: Qt.rgba(1, 1, 1, bridge.dark ? 0.045 : 0.55)
                                                            border.width: 1
                                                            border.color: Qt.rgba(1, 1, 1, bridge.dark ? 0.08 : 0.45)
                                                            Rectangle {
                                                                width: 3
                                                                height: 18
                                                                radius: 1.5
                                                                anchors.left: parent.left
                                                                anchors.leftMargin: 8
                                                                anchors.verticalCenter: parent.verticalCenter
                                                                color: "#ff7a45"
                                                            }
                                                            Column {
                                                                anchors.left: parent.left
                                                                anchors.right: parent.right
                                                                anchors.leftMargin: 20
                                                                anchors.rightMargin: 10
                                                                anchors.verticalCenter: parent.verticalCenter
                                                                spacing: 2
                                                                Text {
                                                                    width: parent.width
                                                                    text: modelData.name
                                                                    color: side.ink
                                                                    font.pixelSize: 13
                                                                    font.bold: true
                                                                    elide: Text.ElideRight
                                                                }
                                                                Text {
                                                                    width: parent.width
                                                                    text: modelData.kuid
                                                                    color: side.mute
                                                                    font.pixelSize: 11
                                                                    font.family: "Consolas"
                                                                    elide: Text.ElideMiddle
                                                                }
                                                            }
                                                            TapHandler { onTapped: root.openDependency(modelData.kuid) }
                                                        }
                                                    }
                                                }
                                            }
                                            TapHandler {
                                                onTapped: function (eventPoint) {
                                                    if (depBlock.visible) {
                                                        var local = depBlock.mapFromItem(assetCard, eventPoint.position.x, eventPoint.position.y)
                                                        if (local.x >= 0 && local.y >= 0 && local.x <= depBlock.width && local.y <= depBlock.height)
                                                            return
                                                    }
                                                    bridge.focusAsset(modelData.kuid)
                                                }
                                            }
                                        }
                                    }
                                }
                        }
                    }
                }

                GlassPlate {
                    id: queueWell
                    property bool active: false
                    visible: false
                    height: 0
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.bottom: parent.bottom
                    sunk: true
                    dark: bridge.dark
                    plateRadius: 14
                    foot: 4

                    Column {
                        anchors.fill: parent
                        spacing: 6
                        Text {
                            text: "Packages"
                            color: side.mute
                            font.pixelSize: 11
                        }
                        ListView {
                            id: sourceList
                            width: parent.width
                            height: Math.max(0, parent.height - 22)
                            clip: true
                            spacing: 4
                            boundsBehavior: Flickable.StopAtBounds
                            model: sourceModel
                            delegate: Rectangle {
                                required property string sourceId
                                required property string name
                                required property string kind
                                required property string size
                                required property string status
                                width: sourceList.width
                                height: 48
                                radius: 10
                                color: root._selected === sourceId
                                       ? Qt.rgba(1, 0.35, 0.12, bridge.dark ? 0.28 : 0.18)
                                       : Qt.rgba(1, 1, 1, bridge.dark ? 0.05 : 0.45)
                                Column {
                                    anchors.fill: parent
                                    anchors.margins: 8
                                    spacing: 2
                                    Text {
                                        width: parent.width - 20
                                        text: name
                                        color: side.ink
                                        font.pixelSize: 12
                                        font.bold: true
                                        elide: Text.ElideRight
                                    }
                                    Text {
                                        width: parent.width
                                        text: kind + "  ·  " + size + "  ·  " + status
                                        color: side.mute
                                        font.pixelSize: 11
                                        elide: Text.ElideRight
                                    }
                                }
                                Text {
                                    anchors.right: parent.right
                                    anchors.top: parent.top
                                    anchors.margins: 4
                                    text: "×"
                                    color: side.mute
                                    font.pixelSize: 14
                                    TapHandler { onTapped: bridge.removeSource(sourceId) }
                                }
                                TapHandler { onTapped: { root._selected = sourceId; bridge.selectSource(sourceId) } }
                            }
                        }
                    }
                }
            }

        }

        GlassPlate {
            anchors.left: parent.left
            anchors.leftMargin: root.sideLayout + 10
            anchors.right: parent.right
            anchors.rightMargin: root.taskLayout + 10
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            anchors.bottomMargin: chrome.contentInset(nav.height)
            dark: bridge.dark
            plateRadius: 16
            foot: 8

            Item {
                id: mid
                    anchors.fill: parent
                    anchors.margins: 8
                    DropArea {
                        anchors.fill: parent
                        enabled: bridge.page === "install"
                        z: 4
                        onDropped: function (drop) {
                            var urls = []
                            for (var i = 0; i < drop.urls.length; ++i)
                                urls.push(String(drop.urls[i]))
                            bridge.dropUrls(urls)
                            drop.acceptProposedAction()
                        }
                    }
                    property real nameW: 240
                    property real statW: 88
                    property real modifiedW: 118
                    property real sizeW: 56
                    property real kuidW: 136
                    property real authorW: 100
                    property real buildW: 72
                    property real catW: 220
                    property real tableW: 18 + nameW + statW + modifiedW + sizeW + kuidW + authorW + buildW + catW + 64

                    Row {
                        id: head
                        anchors.top: parent.top
                        anchors.left: parent.left
                        anchors.right: parent.right
                        height: 36
                        spacing: 6
                        RaiseButton {
                            visible: bridge.page === "files"
                            width: 64
                            height: 32
                            label: "Back"
                            onClicked: bridge.backContents()
                        }
                        Text {
                            width: bridge.libraryOn
                                  ? Math.max(80, parent.width - 220 - 80 - 18)
                                  : (bridge.page === "backups"
                                     ? Math.max(80, parent.width - 8)
                                     : (bridge.page === "install"
                                        ? Math.max(80, parent.width - 96 - 72 - 64 - 72 - 30)
                                        : (bridge.page === "encrypt"
                                           ? Math.max(80, parent.width - 72 - 96 - 72 - 24)
                                           : Math.max(80, parent.width - 64 - 88 - 100 - 24))))
                            height: 32
                            verticalAlignment: Text.AlignVCenter
                            text: bridge.libraryOn
                                  ? bridge.librarySummary
                                  : (bridge.page === "backups"
                                     ? bridge.backupSummary
                                     : (bridge.page === "install"
                                        ? (sourceModel.count ? sourceModel.count + " packages" : "Drop zip or CDP")
                                        : (bridge.page === "encrypt"
                                           ? (scriptModel.count ? scriptModel.count + " scripts" : "Drop .gs files")
                                           : bridge.crumb)))
                            color: bridge.dark ? "#f4f6fa" : "#1d1d1f"
                            font.pixelSize: 13
                            font.bold: true
                            elide: Text.ElideRight
                        }
                        Rectangle {
                            visible: bridge.libraryOn
                            width: bridge.libraryOn ? 220 : 0
                            height: 32
                            radius: 8
                            color: Qt.rgba(0, 0, 0, bridge.dark ? 0.38 : 0.08)
                            border.width: 1
                            border.color: Qt.rgba(1, 1, 1, bridge.dark ? 0.08 : 0.35)
                            TextInput {
                                id: findInput
                                anchors.fill: parent
                                anchors.leftMargin: 8
                                anchors.rightMargin: 8
                                verticalAlignment: TextInput.AlignVCenter
                                color: bridge.dark ? "#f4f6fa" : "#1c1c1e"
                                font.pixelSize: 12
                                selectByMouse: true
                                clip: true
                                Text {
                                    anchors.fill: parent
                                    verticalAlignment: Text.AlignVCenter
                                    visible: !findInput.text.length && !findInput.activeFocus
                                    text: "Find"
                                    color: bridge.dark ? "#8b93a1" : "#5c6570"
                                    font.pixelSize: 12
                                }
                                onTextChanged: findWait.restart()
                                Timer {
                                    id: findWait
                                    interval: 80
                                    onTriggered: bridge.filterLibrary(findInput.text)
                                }
                            }
                        }
                        RaiseButton {
                            visible: bridge.libraryOn
                            width: 72
                            height: 32
                            label: "Scan"
                            onClicked: bridge.scanLibrary()
                        }
                        RaiseButton {
                            visible: bridge.page === "install"
                            width: 96
                            height: 32
                            label: "Install"
                            accent: true
                            onClicked: bridge.installChecked()
                        }
                        RaiseButton {
                            visible: bridge.page === "install"
                            width: 72
                            height: 32
                            label: "Stop"
                            onClicked: bridge.stopQueue()
                        }
                        RaiseButton {
                            visible: bridge.page === "files"
                            width: 88
                            height: 32
                            label: "All"
                            onClicked: setAll(true)
                        }
                        RaiseButton {
                            visible: bridge.page === "files"
                            width: 100
                            height: 32
                            label: "None"
                            onClicked: setAll(false)
                        }
                        RaiseButton {
                            visible: bridge.page === "install"
                            width: 64
                            height: 32
                            label: "All"
                            onClicked: bridge.setSourcesChecked(true)
                        }
                        RaiseButton {
                            visible: bridge.page === "install"
                            width: 72
                            height: 32
                            label: "None"
                            onClicked: bridge.setSourcesChecked(false)
                        }
                        RaiseButton {
                            visible: bridge.page === "encrypt"
                            width: 72
                            height: 32
                            label: "Add"
                            onClicked: bridge.addScripts()
                        }
                        RaiseButton {
                            visible: bridge.page === "encrypt"
                            width: 96
                            height: 32
                            label: "Encrypt"
                            accent: true
                            onClicked: bridge.encryptScripts()
                        }
                        RaiseButton {
                            visible: bridge.page === "encrypt"
                            width: 72
                            height: 32
                            label: "Clear"
                            onClicked: bridge.clearScripts()
                        }
                    }

                    Row {
                        id: tools
                        visible: bridge.libraryOn
                        height: bridge.libraryOn ? 34 : 0
                        anchors.top: head.bottom
                        anchors.topMargin: bridge.libraryOn ? 6 : 0
                        anchors.left: parent.left
                        anchors.right: parent.right
                        spacing: 6
                        RaiseButton { width: 72; height: 30; label: "Status"; onClicked: bridge.inspectStatus() }
                        RaiseButton { width: 72; height: 30; label: "Errors"; onClicked: bridge.inspectErrors() }
                        RaiseButton { width: 88; height: 30; label: "Depends"; onClicked: bridge.inspectDepends() }
                        RaiseButton { width: 64; height: 30; label: "Size"; onClicked: bridge.measurePacked() }
                        RaiseButton { width: 72; height: 30; label: "Tuner"; accent: true; onClicked: bridge.openEngine("") }
                        RaiseButton { width: 78; height: 30; label: "Export"; onClicked: bridge.exportTogether() }
                        RaiseButton { width: 88; height: 30; label: "Each CDP"; onClicked: bridge.exportEach() }
                        RaiseButton { width: 64; height: 30; label: "All"; onClicked: bridge.pickVisible(true) }
                        RaiseButton { width: 64; height: 30; label: "None"; onClicked: bridge.pickVisible(false) }
                    }

                    Flickable {
                        id: hFlick
                        visible: bridge.libraryOn
                        anchors.top: tools.bottom
                        anchors.bottom: parent.bottom
                        anchors.left: parent.left
                        anchors.right: parent.right
                        contentWidth: mid.tableW
                        contentHeight: height
                        clip: true
                        boundsBehavior: Flickable.StopAtBounds
                        flickableDirection: Flickable.HorizontalFlick
                        interactive: contentWidth > width + 2

                        Item {
                            width: mid.tableW
                            height: hFlick.height

                    Row {
                        id: colHead
                        visible: bridge.libraryOn
                        height: bridge.libraryOn ? 22 : 0
                        anchors.top: parent.top
                        anchors.left: parent.left
                        spacing: 8
                        Item { width: 18; height: 1 }
                        ColHead { title: "Name"; key: "name"; field: "name" }
                        ColHead { title: "Status"; key: "status"; field: "status" }
                        ColHead { title: "Modification Date"; key: "modified"; field: "modified" }
                        ColHead { title: "File Size"; key: "size"; field: "size" }
                        ColHead { title: "Asset ID"; key: "kuid"; field: "kuid" }
                        ColHead { title: "Author Username"; key: "author"; field: "author" }
                        ColHead { title: "Build Version"; key: "build"; field: "build" }
                        ColHead { title: "Type"; key: "type"; field: "type" }
                    }
                    ListView {
                        id: libraryList
                        visible: bridge.libraryOn
                        anchors.top: colHead.bottom
                        anchors.bottom: parent.bottom
                        anchors.bottomMargin: bridge.reportOn ? 168 : 12
                        anchors.left: parent.left
                        width: mid.tableW
                        anchors.topMargin: 4
                        clip: true
                        boundsBehavior: Flickable.StopAtBounds
                        spacing: 2
                        cacheBuffer: 800
                        model: bridge.libraryModel
                        delegate: Rectangle {
                            id: rowRect
                            required property string kuid
                            required property string assetName
                            required property bool faulty
                            required property string category
                            required property string credits
                            required property bool picked
                            required property string packed
                            required property bool engineSpec
                            required property string statusText
                            required property string modified
                            required property string authorName
                            required property string buildVersion
                            width: libraryList.width
                            height: 32
                            radius: 6
                            border.width: bridge.detailKuid === kuid ? 1 : 0
                            border.color: "#ff5a1f"
                            color: faulty
                                   ? Qt.rgba(0.78, 0.16, 0.14, picked ? 0.72 : (bridge.dark ? 0.5 : 0.28))
                                   : (picked
                                      ? Qt.rgba(1, 0.35, 0.12, bridge.dark ? 0.38 : 0.22)
                                      : Qt.rgba(0, 0, 0, bridge.dark ? 0.18 : 0.05))
                            Row {
                                anchors.fill: parent
                                anchors.leftMargin: 6
                                anchors.rightMargin: engineSpec ? 64 : 6
                                spacing: 8
                                Rectangle {
                                    id: checkBox
                                    width: 16
                                    height: 16
                                    radius: 4
                                    anchors.verticalCenter: parent.verticalCenter
                                    color: picked ? "#ff5a1f" : Qt.rgba(0, 0, 0, bridge.dark ? 0.35 : 0.08)
                                    border.width: 1
                                    border.color: Qt.rgba(1, 1, 1, 0.25)
                                    Text {
                                        anchors.centerIn: parent
                                        visible: picked
                                        text: "✓"
                                        color: "#ffffff"
                                        font.pixelSize: 11
                                    }
                                    MouseArea {
                                        id: pickDrag
                                        property bool keyed: false
                                        anchors.fill: parent
                                        anchors.margins: -6
                                        preventStealing: true
                                        onPressed: function (mouse) {
                                            keyed = (mouse.modifiers & (Qt.ShiftModifier | Qt.ControlModifier)) !== 0
                                            if (keyed) {
                                                bridge.clickPick(kuid, mouse.modifiers)
                                                return
                                            }
                                            bridge.beginDragPick(kuid)
                                        }
                                        onPositionChanged: function (mouse) {
                                            if (!pressed || keyed)
                                                return
                                            var local = mapToItem(libraryList, mouse.x, mouse.y)
                                            var idx = libraryList.indexAt(8, local.y + libraryList.contentY)
                                            if (idx < 0)
                                                return
                                            var row = libraryList.itemAtIndex(idx)
                                            if (row)
                                                bridge.dragPick(row.kuid)
                                        }
                                        onReleased: {
                                            if (!keyed)
                                                bridge.endDragPick()
                                        }
                                        onCanceled: {
                                            if (!keyed)
                                                bridge.endDragPick()
                                        }
                                    }
                                }
                                Text {
                                    width: mid.nameW
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: assetName
                                    color: faulty ? "#ffd0cc" : (bridge.dark ? "#f4f6fa" : "#1d1d1f")
                                    font.pixelSize: 12
                                    font.bold: faulty
                                    elide: Text.ElideRight
                                }
                                Text {
                                    width: mid.statW
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: statusText
                                    color: statusText.indexOf("Edit") >= 0 ? "#ff5a1f" : (faulty ? "#ffb0a8" : (bridge.dark ? "#d5dbe3" : "#1d1d1f"))
                                    font.pixelSize: 11
                                    font.bold: faulty || statusText.indexOf("Edit") >= 0
                                    elide: Text.ElideRight
                                }
                                Text {
                                    width: mid.modifiedW
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: modified
                                    color: bridge.dark ? "#d5dbe3" : "#1d1d1f"
                                    font.pixelSize: 11
                                    elide: Text.ElideRight
                                }
                                Text {
                                    width: mid.sizeW
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: packed
                                    color: bridge.dark ? "#d5dbe3" : "#1d1d1f"
                                    font.pixelSize: 11
                                    elide: Text.ElideRight
                                }
                                Text {
                                    width: mid.kuidW
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: kuid
                                    color: faulty ? "#ffb0a8" : (bridge.dark ? "#9aa3b2" : "#5c6570")
                                    font.pixelSize: 11
                                    elide: Text.ElideRight
                                }
                                Text {
                                    width: mid.authorW
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: authorName
                                    color: bridge.dark ? "#d5dbe3" : "#1d1d1f"
                                    font.pixelSize: 11
                                    elide: Text.ElideRight
                                }
                                Text {
                                    width: mid.buildW
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: buildVersion
                                    color: bridge.dark ? "#d5dbe3" : "#1d1d1f"
                                    font.pixelSize: 11
                                    elide: Text.ElideRight
                                }
                                Text {
                                    width: mid.catW
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: category
                                    color: bridge.dark ? "#9aa3b2" : "#5c6570"
                                    font.pixelSize: 11
                                    elide: Text.ElideRight
                                }
                            }
                            RaiseButton {
                                id: tunerBtn
                                visible: engineSpec
                                anchors.right: parent.right
                                anchors.rightMargin: 4
                                anchors.verticalCenter: parent.verticalCenter
                                width: 58
                                height: 22
                                label: "Tuner"
                                accent: true
                                onClicked: bridge.openEngine(kuid)
                            }
                            TapHandler {
                                onTapped: function (eventPoint) {
                                    var box = checkBox.mapFromItem(rowRect, eventPoint.position.x, eventPoint.position.y)
                                    if (box.x >= -8 && box.y >= -8 && box.x <= checkBox.width + 8 && box.y <= checkBox.height + 8)
                                        return
                                    if (tunerBtn.visible) {
                                        var local = tunerBtn.mapFromItem(rowRect, eventPoint.position.x, eventPoint.position.y)
                                        if (local.x >= 0 && local.y >= 0 && local.x <= tunerBtn.width && local.y <= tunerBtn.height)
                                            return
                                    }
                                    bridge.clickPick(kuid, eventPoint.modifiers)
                                }
                            }
                        }
                    }
                        }
                    }

                    Rectangle {
                        id: hBar
                        visible: bridge.libraryOn && hFlick.contentWidth > hFlick.width + 4
                        height: 8
                        radius: 4
                        color: "#ff5a1f"
                        anchors.bottom: parent.bottom
                        anchors.bottomMargin: bridge.reportOn ? 168 : 0
                        width: Math.max(28, hFlick.visibleArea.widthRatio * hFlick.width)
                        Binding on x {
                            when: !hDrag.drag.active
                            value: hFlick.x + hFlick.visibleArea.xPosition * Math.max(0, hFlick.width - width)
                        }
                        MouseArea {
                            id: hDrag
                            anchors.fill: parent
                            anchors.margins: -8
                            preventStealing: true
                            drag.target: hBar
                            drag.axis: Drag.XAxis
                            drag.minimumX: hFlick.x
                            drag.maximumX: Math.max(hFlick.x, hFlick.x + hFlick.width - hBar.width)
                            onPositionChanged: {
                                if (!drag.active)
                                    return
                                var travel = hFlick.width - hBar.width
                                var frac = travel <= 1 ? 0 : (hBar.x - hFlick.x) / travel
                                hFlick.contentX = frac * Math.max(0, hFlick.contentWidth - hFlick.width)
                            }
                        }
                    }

                    Rectangle {
                        id: reportBox
                        visible: bridge.reportOn
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.bottom: parent.bottom
                        height: visible ? 160 : 0
                        radius: 10
                        color: Qt.rgba(0, 0, 0, bridge.dark ? 0.45 : 0.08)
                        border.width: 1
                        border.color: Qt.rgba(1, 1, 1, 0.12)
                        Flickable {
                            anchors.fill: parent
                            anchors.margins: 8
                            anchors.rightMargin: 36
                            contentWidth: width
                            contentHeight: reportBody.height
                            clip: true
                            boundsBehavior: Flickable.StopAtBounds
                            Text {
                                id: reportBody
                                width: reportBox.width - 44
                                wrapMode: Text.Wrap
                                text: bridge.reportText
                                color: bridge.dark ? "#f4f6fa" : "#1d1d1f"
                                font.pixelSize: 12
                            }
                        }
                        Text {
                            anchors.right: parent.right
                            anchors.top: parent.top
                            anchors.margins: 6
                            text: "×"
                            color: "#ff5a1f"
                            font.pixelSize: 16
                            TapHandler { onTapped: bridge.closeReport() }
                        }
                    }

                    Rectangle {
                        id: libBar
                        visible: bridge.libraryOn && libraryList.contentHeight > libraryList.height + 4
                        width: 8
                        radius: 4
                        color: "#ff5a1f"
                        anchors.right: parent.right
                        height: Math.max(28, libraryList.visibleArea.heightRatio * libraryList.height)
                        Binding on y {
                            when: !libDrag.drag.active
                            value: hFlick.y + colHead.height + libraryList.visibleArea.yPosition * Math.max(0, libraryList.height - height)
                        }
                        MouseArea {
                            id: libDrag
                            anchors.fill: parent
                            anchors.margins: -8
                            drag.target: libBar
                            drag.axis: Drag.YAxis
                            drag.minimumY: hFlick.y + colHead.height
                            drag.maximumY: Math.max(hFlick.y + colHead.height, hFlick.y + colHead.height + libraryList.height - libBar.height)
                            onPositionChanged: {
                                if (!drag.active)
                                    return
                                var origin = hFlick.y + colHead.height
                                var travel = libraryList.height - libBar.height
                                var frac = travel <= 1 ? 0 : (libBar.y - origin) / travel
                                libraryList.contentY = frac * Math.max(0, libraryList.contentHeight - libraryList.height)
                            }
                        }
                    }

                    ListView {
                        id: installList
                        visible: bridge.page === "install"
                        anchors.top: head.bottom
                        anchors.bottom: parent.bottom
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.topMargin: 6
                        clip: true
                        spacing: 6
                        boundsBehavior: Flickable.StopAtBounds
                        model: sourceModel

                        Text {
                            anchors.centerIn: parent
                            visible: sourceModel.count === 0
                            text: "Drop zip or CDP files here"
                            color: bridge.dark ? "#9aa3b2" : "#5c6570"
                            font.pixelSize: 16
                        }
                        delegate: Rectangle {
                            required property int index
                            required property string sourceId
                            required property string name
                            required property string kind
                            required property string size
                            required property string status
                            required property int percent
                            required property bool checked
                            readonly property bool failed: status.indexOf("Failed") >= 0
                            readonly property bool done: percent >= 100 && !failed
                            width: installList.width
                            height: 68
                            radius: 10
                            color: Qt.rgba(0, 0, 0, bridge.dark ? 0.18 : 0.05)
                            Row {
                                anchors.fill: parent
                                anchors.margins: 8
                                spacing: 8
                                Rectangle {
                                    width: 18
                                    height: 18
                                    radius: 5
                                    anchors.verticalCenter: parent.verticalCenter
                                    color: checked ? "#ff5a1f" : Qt.rgba(0, 0, 0, bridge.dark ? 0.35 : 0.08)
                                    border.width: 1
                                    border.color: Qt.rgba(1, 1, 1, 0.25)
                                    Text {
                                        anchors.centerIn: parent
                                        visible: checked
                                        text: "✓"
                                        color: "#ffffff"
                                        font.pixelSize: 12
                                    }
                                }
                                Column {
                                    width: parent.width - 18 - 150 - 28 - 24
                                    anchors.verticalCenter: parent.verticalCenter
                                    spacing: 4
                                    Text {
                                        width: parent.width
                                        text: name
                                        color: bridge.dark ? "#f4f6fa" : "#1d1d1f"
                                        font.pixelSize: 13
                                        font.bold: true
                                        elide: Text.ElideRight
                                    }
                                    Text {
                                        width: parent.width
                                        text: kind + "  ·  " + size
                                        color: bridge.dark ? "#9aa3b2" : "#5c6570"
                                        font.pixelSize: 11
                                        elide: Text.ElideRight
                                    }
                                    Rectangle {
                                        width: parent.width
                                        height: 6
                                        radius: 3
                                        color: Qt.rgba(1, 1, 1, bridge.dark ? 0.08 : 0.45)
                                        Rectangle {
                                            width: parent.width * Math.max(0, Math.min(100, percent)) / 100
                                            height: parent.height
                                            radius: 3
                                            color: failed ? "#ff5a1f" : (done ? "#3ddc84" : "#ff5a1f")
                                        }
                                    }
                                }
                                Column {
                                    width: 150
                                    anchors.verticalCenter: parent.verticalCenter
                                    spacing: 2
                                    Text {
                                        width: parent.width
                                        text: percent + "%"
                                        color: done ? "#3ddc84" : (failed ? "#ff5a1f" : (bridge.dark ? "#f4f6fa" : "#1d1d1f"))
                                        font.pixelSize: 13
                                        font.bold: true
                                        horizontalAlignment: Text.AlignRight
                                    }
                                    Text {
                                        width: parent.width
                                        text: status
                                        color: failed ? "#ff5a1f" : (bridge.dark ? "#9aa3b2" : "#5c6570")
                                        font.pixelSize: 11
                                        horizontalAlignment: Text.AlignRight
                                        elide: Text.ElideLeft
                                    }
                                }
                                Text {
                                    width: 20
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: "×"
                                    color: bridge.dark ? "#9aa3b2" : "#5c6570"
                                    font.pixelSize: 16
                                    horizontalAlignment: Text.AlignRight
                                    TapHandler { onTapped: bridge.removeSource(sourceId) }
                                }
                            }
                            TapHandler {
                                onTapped: function (eventPoint) {
                                    root.rangeCheck(sourceModel, index, eventPoint.modifiers, "srcAnchor", "")
                                }
                            }
                        }
                    }

                    GlassPlate {
                        id: backupBar
                        visible: bridge.page === "backups"
                        height: visible ? 76 : 0
                        anchors.top: head.bottom
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.topMargin: visible ? 6 : 0
                        z: 6
                        dark: bridge.dark
                        plateRadius: 24
                        foot: 8

                        component SlidePick: Item {
                            property string leftLabel: ""
                            property string rightLabel: ""
                            property bool leftHot: true
                            signal leftPicked()
                            signal rightPicked()
                            width: 176
                            height: 44
                            function place(animate) {
                                var chip = leftHot ? leftChip : rightChip
                                var at = chip.mapToItem(pick, 0, 0)
                                if (!animate) {
                                    pill.x = at.x
                                    pill.width = chip.width
                                    return
                                }
                                slideX.to = at.x
                                slideW.to = chip.width
                                slideX.start()
                                slideW.start()
                            }
                            onLeftHotChanged: place(true)
                            Component.onCompleted: place(false)
                            Item {
                                id: pick
                                anchors.fill: parent
                                Rectangle {
                                    anchors.fill: parent
                                    anchors.topMargin: 2
                                    anchors.bottomMargin: 2
                                    radius: 16
                                    color: Qt.rgba(0, 0, 0, bridge.dark ? 0.32 : 0.06)
                                    border.width: 1
                                    border.color: Qt.rgba(1, 1, 1, bridge.dark ? 0.08 : 0.40)
                                }
                                Rectangle {
                                    id: pill
                                    z: 1
                                    y: 6
                                    x: 4
                                    width: 80
                                    height: 32
                                    radius: 12
                                    color: "#ff5a1f"
                                }
                                NumberAnimation { id: slideX; target: pill; property: "x"; duration: 240; easing.type: Easing.OutCubic }
                                NumberAnimation { id: slideW; target: pill; property: "width"; duration: 240; easing.type: Easing.OutCubic }
                                Item {
                                    id: leftChip
                                    x: 4
                                    width: (parent.width - 8) / 2
                                    height: parent.height
                                    z: 2
                                    Text {
                                        anchors.centerIn: parent
                                        text: leftLabel
                                        color: leftHot ? "#ffffff" : (bridge.dark ? "#f4f6fa" : "#1c1c1e")
                                        font.pixelSize: 13
                                        font.bold: leftHot
                                    }
                                    TapHandler { onTapped: leftPicked() }
                                }
                                Item {
                                    id: rightChip
                                    x: 4 + (parent.width - 8) / 2
                                    width: (parent.width - 8) / 2
                                    height: parent.height
                                    z: 2
                                    Text {
                                        anchors.centerIn: parent
                                        text: rightLabel
                                        color: !leftHot ? "#ffffff" : (bridge.dark ? "#f4f6fa" : "#1c1c1e")
                                        font.pixelSize: 13
                                        font.bold: !leftHot
                                    }
                                    TapHandler { onTapped: rightPicked() }
                                }
                            }
                        }

                        Item {
                            anchors.fill: parent
                            anchors.leftMargin: 12
                            anchors.rightMargin: 12
                            anchors.topMargin: 8
                            anchors.bottomMargin: 8
                            SlidePick {
                                id: kindPick
                                anchors.left: parent.left
                                anchors.verticalCenter: parent.verticalCenter
                                leftLabel: "Folder"
                                rightLabel: "tzarc"
                                leftHot: root.backupKind === "Folder"
                                onLeftPicked: root.backupKind = "Folder"
                                onRightPicked: root.backupKind = "tzarc"
                            }
                            SlidePick {
                                id: orderPick
                                anchors.right: parent.right
                                anchors.verticalCenter: parent.verticalCenter
                                width: 188
                                leftLabel: "Newest"
                                rightLabel: "Oldest"
                                leftHot: root.backupOrder === "new"
                                onLeftPicked: root.backupOrder = "new"
                                onRightPicked: root.backupOrder = "old"
                            }
                            Rectangle {
                                anchors.left: kindPick.right
                                anchors.right: orderPick.left
                                anchors.leftMargin: 10
                                anchors.rightMargin: 10
                                anchors.verticalCenter: parent.verticalCenter
                                height: 40
                                radius: 12
                                color: Qt.rgba(0, 0, 0, bridge.dark ? 0.38 : 0.08)
                                border.width: 1
                                border.color: Qt.rgba(1, 1, 1, bridge.dark ? 0.08 : 0.35)
                                TextInput {
                                    id: backupFind
                                    anchors.fill: parent
                                    anchors.leftMargin: 12
                                    anchors.rightMargin: 12
                                    verticalAlignment: TextInput.AlignVCenter
                                    color: bridge.dark ? "#f4f6fa" : "#1c1c1e"
                                    font.pixelSize: 13
                                    selectByMouse: true
                                    clip: true
                                    Text {
                                        anchors.fill: parent
                                        verticalAlignment: Text.AlignVCenter
                                        visible: !backupFind.text.length && !backupFind.activeFocus
                                        text: "Name or KUID"
                                        color: bridge.dark ? "#8b93a1" : "#5c6570"
                                        font.pixelSize: 13
                                    }
                                    onTextChanged: backupWait.restart()
                                    Timer {
                                        id: backupWait
                                        interval: 160
                                        onTriggered: {
                                            if (bridge.page === "backups")
                                                bridge.findBackups(backupFind.text)
                                        }
                                    }
                                }
                                Connections {
                                    target: bridge
                                    function onChanged() {
                                        if (backupFind.activeFocus)
                                            return
                                        if (backupFind.text !== bridge.backupQuery)
                                            backupFind.text = bridge.backupQuery
                                    }
                                }
                            }
                        }
                    }

                    ListView {
                        id: backupList
                        visible: bridge.page === "backups"
                        anchors.top: backupBar.bottom
                        anchors.bottom: parent.bottom
                        anchors.bottomMargin: 8
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.topMargin: 8
                        clip: true
                        spacing: 6
                        boundsBehavior: Flickable.StopAtBounds
                        model: backupModel
                        section.property: "day"
                        section.criteria: ViewSection.FullString
                        section.delegate: Item {
                            required property string section
                            width: backupList.width
                            height: 28
                            Text {
                                anchors.left: parent.left
                                anchors.bottom: parent.bottom
                                anchors.bottomMargin: 4
                                text: section
                                color: "#ff5a1f"
                                font.pixelSize: 12
                                font.bold: true
                            }
                        }
                        delegate: Rectangle {
                            required property int index
                            required property string title
                            required property string detail
                            required property string path
                            readonly property bool picked: root.bagOn(root.backupBag, path) || path === bridge.backupPick
                            width: backupList.width
                            height: 58
                            radius: 12
                            color: picked
                                   ? Qt.rgba(1, 0.35, 0.12, bridge.dark ? 0.28 : 0.16)
                                   : Qt.rgba(0, 0, 0, bridge.dark ? 0.22 : 0.05)
                            border.width: 1
                            border.color: picked ? "#ff5a1f" : Qt.rgba(1, 1, 1, bridge.dark ? 0.06 : 0.28)
                            TapHandler {
                                onTapped: function (eventPoint) {
                                    root.rangeBag(root.idsOf(backupModel, "path"), index, eventPoint.modifiers, "backupAnchor", "backupBag")
                                    if ((eventPoint.modifiers & (Qt.ShiftModifier | Qt.ControlModifier)) === 0)
                                        bridge.showBackup(path)
                                }
                            }
                            Row {
                                anchors.fill: parent
                                anchors.leftMargin: 12
                                anchors.rightMargin: 8
                                spacing: 10
                                Column {
                                    width: parent.width - 74
                                    anchors.verticalCenter: parent.verticalCenter
                                    spacing: 3
                                    Text {
                                        width: parent.width
                                        text: title
                                        color: bridge.dark ? "#f4f6fa" : "#1d1d1f"
                                        font.pixelSize: 13
                                        elide: Text.ElideMiddle
                                    }
                                    Text {
                                        width: parent.width
                                        text: detail
                                        color: bridge.dark ? "#9aa3b2" : "#5c6570"
                                        font.pixelSize: 11
                                        elide: Text.ElideMiddle
                                    }
                                }
                                RaiseButton {
                                    width: 64
                                    height: 30
                                    anchors.verticalCenter: parent.verticalCenter
                                    label: "Open"
                                    onClicked: bridge.openBackup(path)
                                }
                            }
                        }
                    }
                    Text {
                        visible: bridge.page === "backups" && backupModel.count === 0
                        anchors.horizontalCenter: parent.horizontalCenter
                        anchors.top: backupBar.bottom
                        anchors.topMargin: 48
                        width: Math.max(120, parent.width - 48)
                        horizontalAlignment: Text.AlignHCenter
                        wrapMode: Text.Wrap
                        text: "No " + root.backupKind + " copies"
                              + (backupFind.text.length ? " for this search." : ".")
                        color: bridge.dark ? "#9aa3b2" : "#5c6570"
                        font.pixelSize: 14
                    }

                    ListView {
                        id: scriptList
                        visible: bridge.page === "encrypt"
                        anchors.top: head.bottom
                        anchors.bottom: parent.bottom
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.topMargin: 6
                        clip: true
                        spacing: 6
                        boundsBehavior: Flickable.StopAtBounds
                        model: scriptModel

                        DropArea {
                            anchors.fill: parent
                            z: 2
                            onDropped: function (drop) {
                                var urls = []
                                for (var i = 0; i < drop.urls.length; ++i)
                                    urls.push(String(drop.urls[i]))
                                bridge.dropUrls(urls)
                                drop.acceptProposedAction()
                            }
                        }
                        Text {
                            anchors.centerIn: parent
                            visible: scriptModel.count === 0
                            text: "Drop .gs files or a folder — .gse is written beside each script"
                            color: bridge.dark ? "#9aa3b2" : "#5c6570"
                            font.pixelSize: 15
                        }
                        delegate: Rectangle {
                            required property int index
                            required property string scriptId
                            required property string name
                            required property string folder
                            required property string status
                            required property string tone
                            readonly property bool marked: root.bagOn(root.scriptBag, scriptId)
                            width: scriptList.width
                            height: 52
                            radius: 10
                            color: marked
                                   ? Qt.rgba(1, 0.35, 0.12, bridge.dark ? 0.28 : 0.18)
                                   : Qt.rgba(0, 0, 0, bridge.dark ? 0.18 : 0.05)
                            border.width: marked ? 1 : 0
                            border.color: "#ff5a1f"
                            TapHandler {
                                onTapped: function (eventPoint) {
                                    root.rangeBag(root.idsOf(scriptModel, "scriptId"), index, eventPoint.modifiers, "scriptAnchor", "scriptBag")
                                }
                            }
                            Row {
                                anchors.fill: parent
                                anchors.margins: 8
                                spacing: 8
                                Column {
                                    width: parent.width - 160 - 28
                                    anchors.verticalCenter: parent.verticalCenter
                                    spacing: 2
                                    Text {
                                        width: parent.width
                                        text: name
                                        color: bridge.dark ? "#f4f6fa" : "#1d1d1f"
                                        font.pixelSize: 13
                                        font.bold: true
                                        elide: Text.ElideRight
                                    }
                                    Text {
                                        width: parent.width
                                        text: folder
                                        color: bridge.dark ? "#9aa3b2" : "#5c6570"
                                        font.pixelSize: 11
                                        elide: Text.ElideLeft
                                    }
                                }
                                Text {
                                    width: 150
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: status
                                    color: tone === "ok" ? "#3ddc84" : (tone === "bad" ? "#ff5a1f" : (bridge.dark ? "#9aa3b2" : "#5c6570"))
                                    font.pixelSize: 12
                                    horizontalAlignment: Text.AlignRight
                                    elide: Text.ElideLeft
                                }
                                Text {
                                    width: 20
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: "×"
                                    color: bridge.dark ? "#9aa3b2" : "#5c6570"
                                    font.pixelSize: 16
                                    horizontalAlignment: Text.AlignRight
                                    TapHandler { onTapped: bridge.removeScript(scriptId) }
                                }
                            }
                        }
                    }

                    ListView {
                        id: contentList
                        visible: bridge.page === "files"
                        anchors.top: head.bottom
                        anchors.bottom: parent.bottom
                        anchors.bottomMargin: bridge.reportOn ? 168 : 0
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.topMargin: 6
                        clip: true
                        boundsBehavior: Flickable.StopAtBounds
                        model: contentModel
                        delegate: Rectangle {
                            required property int index
                            required property string jobId
                            required property string label
                            required property string kind
                            required property string detail
                            required property bool canInstall
                            required property bool checked
                            required property bool openable
                            required property string state
                            width: contentList.width
                            height: 48
                            radius: 10
                            color: Qt.rgba(0, 0, 0, bridge.dark ? 0.18 : 0.05)
                            Row {
                                anchors.fill: parent
                                anchors.margins: 8
                                spacing: 8
                                Rectangle {
                                    visible: canInstall
                                    width: 18
                                    height: 18
                                    radius: 5
                                    anchors.verticalCenter: parent.verticalCenter
                                    color: checked ? "#ff5a1f" : Qt.rgba(0, 0, 0, bridge.dark ? 0.35 : 0.08)
                                    border.width: 1
                                    border.color: Qt.rgba(1, 1, 1, 0.25)
                                    Text {
                                        anchors.centerIn: parent
                                        visible: checked
                                        text: "✓"
                                        color: "#ffffff"
                                        font.pixelSize: 12
                                    }
                                }
                                Column {
                                    width: parent.width - (canInstall ? 26 : 0) - (openable ? 72 : 0) - 90
                                    anchors.verticalCenter: parent.verticalCenter
                                    spacing: 2
                                    Text {
                                        width: parent.width
                                        text: label
                                        color: bridge.dark ? "#f4f6fa" : "#1d1d1f"
                                        font.pixelSize: 13
                                        elide: Text.ElideRight
                                    }
                                    Text {
                                        width: parent.width
                                        text: detail
                                        color: bridge.dark ? "#9aa3b2" : "#5c6570"
                                        font.pixelSize: 11
                                        elide: Text.ElideRight
                                    }
                                }
                                Text {
                                    width: 80
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: state
                                    color: state === "Failed" ? "#ff5a1f" : (bridge.dark ? "#9aa3b2" : "#5c6570")
                                    font.pixelSize: 11
                                    horizontalAlignment: Text.AlignRight
                                }
                                RaiseButton {
                                    visible: openable
                                    width: 64
                                    height: 28
                                    label: "Open"
                                    onClicked: bridge.openEntry(jobId)
                                }
                            }
                            TapHandler {
                                onTapped: function (eventPoint) {
                                    if (!canInstall)
                                        return
                                    root.rangeCheck(contentModel, index, eventPoint.modifiers, "fileAnchor", "canInstall")
                                }
                            }
                        }
                    }
                }
            }

        GlassPlate {
            id: taskSide
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            width: root.taskVisual
            clip: true
            dark: bridge.dark
            plateRadius: 16
            foot: 8
            readonly property color ink: bridge.dark ? "#f2f4f8" : "#1d1d1f"
            readonly property color mute: bridge.dark ? "#8b93a1" : "#5c6570"

            RaiseButton {
                z: 3
                width: 32
                height: 32
                y: 0
                x: root.taskOpen ? 0 : (parent.width - width) / 2
                glyph: root.taskOpen ? bridge.glyphChevronRight : bridge.glyphChevronLeft
                fontName: bridge.iconFont
                tip: root.taskOpen ? "Collapse" : "Expand"
                onClicked: root.setTaskOpen(!root.taskOpen)
            }

            Column {
                id: taskHead
                visible: root.taskOpen && !taskAnim.running
                anchors.top: parent.top
                anchors.left: parent.left
                anchors.leftMargin: 40
                anchors.right: parent.right
                spacing: 8
                Text {
                    text: "Progress"
                    color: taskSide.ink
                    font.pixelSize: 16
                    font.bold: true
                }
                Text {
                    width: parent.width
                    wrapMode: Text.Wrap
                    text: bridge.taskSummary
                    color: taskSide.mute
                    font.pixelSize: 12
                }
                Rectangle {
                    width: parent.width
                    height: 8
                    radius: 4
                    color: Qt.rgba(0, 0, 0, bridge.dark ? 0.35 : 0.08)
                    Rectangle {
                        width: parent.width * Math.max(0, Math.min(100, bridge.taskPercent)) / 100
                        height: parent.height
                        radius: 4
                        color: bridge.taskPercent >= 100 && bridge.taskSummary.indexOf("failed") < 0
                               ? "#3ddc84"
                               : "#ff7a45"
                    }
                }
            }

            Text {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: taskHead.bottom
                anchors.topMargin: 28
                visible: root.taskOpen && !taskAnim.running && taskModel.count === 0
                wrapMode: Text.Wrap
                horizontalAlignment: Text.AlignHCenter
                text: "Click a row to read its log. Validate, submit, and install each keep their own."
                color: taskSide.mute
                font.pixelSize: 12
            }

            ListView {
                visible: root.taskOpen && !taskAnim.running
                anchors.top: taskHead.bottom
                anchors.topMargin: 14
                anchors.bottom: parent.bottom
                anchors.left: parent.left
                anchors.right: parent.right
                clip: true
                spacing: 10
                boundsBehavior: Flickable.StopAtBounds
                model: taskModel
                delegate: Item {
                    required property int index
                    required property string taskId
                    required property string name
                    required property string action
                    required property string phase
                    required property string detail
                    required property real percent
                    readonly property bool okPhase: phase === "Done" || phase === "Installed"
                    readonly property bool badPhase: phase === "Failed"
                    readonly property bool hot: root.bagOn(root.taskBag, taskId) || taskOpenId === taskId
                    width: ListView.view.width
                    height: detail.length ? 82 : 66
                    Rectangle {
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.top: parent.top
                        anchors.topMargin: 4
                        anchors.bottom: parent.bottom
                        radius: 12
                        color: Qt.rgba(0, 0, 0, bridge.dark ? 0.45 : 0.18)
                    }
                    Rectangle {
                        anchors.fill: parent
                        anchors.bottomMargin: 4
                        radius: 12
                        border.width: 1
                        border.color: hot ? "#ff7a45" : Qt.rgba(1, 1, 1, bridge.dark ? 0.16 : 0.55)
                        gradient: Gradient {
                            GradientStop { position: 0.0; color: bridge.dark ? "#3a414c" : "#f7f8fa" }
                            GradientStop { position: 0.45; color: bridge.dark ? "#2a3038" : "#e6eaef" }
                            GradientStop { position: 1.0; color: bridge.dark ? "#1c2128" : "#cfd6de" }
                        }
                        Rectangle {
                            anchors.top: parent.top
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.margins: 1
                            height: parent.height * 0.42
                            radius: 12
                            gradient: Gradient {
                                GradientStop { position: 0.0; color: Qt.rgba(1, 1, 1, bridge.dark ? 0.10 : 0.45) }
                                GradientStop { position: 1.0; color: Qt.rgba(1, 1, 1, 0) }
                            }
                        }
                    }
                    TapHandler {
                        onTapped: function (eventPoint) {
                            root.rangeBag(root.idsOf(taskModel, "taskId"), index, eventPoint.modifiers, "taskAnchor", "taskBag")
                            if ((eventPoint.modifiers & (Qt.ShiftModifier | Qt.ControlModifier)) === 0)
                                root.openTaskLog(taskId)
                        }
                    }
                    Column {
                        anchors.fill: parent
                        anchors.margins: 10
                        spacing: 4
                        Text {
                            width: parent.width
                            text: name
                            color: taskSide.ink
                            font.pixelSize: 13
                            font.bold: true
                            elide: Text.ElideRight
                        }
                        Text {
                            width: parent.width
                            text: action + "  ·  " + phase
                            color: badPhase ? "#ff7a45" : (okPhase ? "#3ddc84" : taskSide.mute)
                            font.pixelSize: 11
                            font.bold: true
                            elide: Text.ElideRight
                        }
                        Rectangle {
                            width: parent.width
                            height: 4
                            radius: 2
                            color: Qt.rgba(0, 0, 0, bridge.dark ? 0.35 : 0.08)
                            Rectangle {
                                width: parent.width * Math.max(0, Math.min(100, percent)) / 100
                                height: parent.height
                                radius: 2
                                color: badPhase ? "#ff7a45" : (okPhase ? "#3ddc84" : "#ff7a45")
                            }
                        }
                        Text {
                            width: parent.width
                            visible: detail.length > 0
                            text: detail
                            color: taskSide.mute
                            font.pixelSize: 11
                            elide: Text.ElideRight
                        }
                    }
                }
            }
        }

        MouseArea {
            z: 40
            enabled: root.sideOpen && !sideAnim.running
            x: side.x + side.width - 5
            y: 40
            width: 12
            height: Math.max(0, parent.height - 40)
            cursorShape: Qt.SplitHCursor
            preventStealing: true
            property real lastX: 0
            onPressed: {
                root.sideDrag = true
                lastX = mapToItem(stage, mouseX, 0).x
            }
            onPositionChanged: {
                if (!pressed)
                    return
                var now = mapToItem(stage, mouseX, 0).x
                var next = root.fitSide(root.sideVisual + (now - lastX))
                root.sideWant = next
                root.sideLayout = next
                root.sideVisual = next
                lastX = now
            }
            onReleased: root.sideDrag = false
            onCanceled: root.sideDrag = false
        }

        MouseArea {
            z: 40
            enabled: root.taskOpen && !taskAnim.running
            x: taskSide.x - 6
            y: 40
            width: 12
            height: Math.max(0, parent.height - 40)
            cursorShape: Qt.SplitHCursor
            preventStealing: true
            property real lastX: 0
            onPressed: {
                root.taskDrag = true
                lastX = mapToItem(stage, mouseX, 0).x
            }
            onPositionChanged: {
                if (!pressed)
                    return
                var now = mapToItem(stage, mouseX, 0).x
                var next = root.fitTask(root.taskVisual - (now - lastX))
                root.taskWant = next
                root.taskLayout = next
                root.taskVisual = next
                lastX = now
            }
            onReleased: root.taskDrag = false
            onCanceled: root.taskDrag = false
        }

        }
    Item {
        id: nav
        enabled: !root.sheetOn
        readonly property real laneLeft: stage.x + root.sideLayout + 10
        readonly property real laneRight: stage.x + stage.width - root.taskLayout
        readonly property string page: bridge.page
        anchors.bottom: parent.bottom
        anchors.bottomMargin: chrome.barMargin
        width: Math.min(660, Math.max(620, laneRight - laneLeft - 16))
        x: laneLeft + (laneRight - laneLeft - width) / 2
        height: 76
        z: 20
        onPageChanged: cluster.placePill(true)
        Component.onCompleted: cluster.placePill(false)

        GlassPlate {
            anchors.fill: parent
            dark: bridge.dark
            plateRadius: 28
            foot: 10
        }

        Item {
            id: cluster
            anchors.centerIn: parent
            width: 578
            height: 48

            function placePill(animate) {
                var chip = libraryChip
                if (bridge.page === "backups")
                    chip = backupsChip
                else if (bridge.page === "install")
                    chip = installChip
                else if (bridge.page === "files")
                    chip = filesChip
                else if (bridge.page === "encrypt")
                    chip = encryptChip
                var at = chip.mapToItem(cluster, 0, 0)
                if (!animate) {
                    pill.x = at.x
                    pill.width = chip.width
                    return
                }
                slideX.to = at.x
                slideW.to = chip.width
                slideX.start()
                slideW.start()
            }

            Rectangle {
                x: 0
                y: 2
                width: 92
                height: 44
                radius: 16
                color: Qt.rgba(0, 0, 0, bridge.dark ? 0.32 : 0.06)
                border.width: 1
                border.color: Qt.rgba(1, 1, 1, bridge.dark ? 0.08 : 0.40)
            }
            Rectangle {
                x: 98
                y: 2
                width: 108
                height: 44
                radius: 16
                color: Qt.rgba(0, 0, 0, bridge.dark ? 0.32 : 0.06)
                border.width: 1
                border.color: Qt.rgba(1, 1, 1, bridge.dark ? 0.08 : 0.40)
            }
            Rectangle {
                x: 212
                y: 2
                width: 108
                height: 44
                radius: 16
                color: Qt.rgba(0, 0, 0, bridge.dark ? 0.32 : 0.06)
                border.width: 1
                border.color: Qt.rgba(1, 1, 1, bridge.dark ? 0.08 : 0.40)
            }
            Rectangle {
                x: 326
                y: 2
                width: 48
                height: 44
                radius: 16
                color: homeH.hovered ? Qt.rgba(1, 0.35, 0.16, 0.35) : Qt.rgba(0, 0, 0, bridge.dark ? 0.22 : 0.05)
                border.width: 1
                border.color: Qt.rgba(1, 1, 1, bridge.dark ? 0.16 : 0.55)
            }
            Rectangle {
                x: 380
                y: 2
                width: 92
                height: 44
                radius: 16
                color: Qt.rgba(0, 0, 0, bridge.dark ? 0.32 : 0.06)
                border.width: 1
                border.color: Qt.rgba(1, 1, 1, bridge.dark ? 0.08 : 0.40)
            }
            Rectangle {
                x: 478
                y: 2
                width: 100
                height: 44
                radius: 16
                color: Qt.rgba(0, 0, 0, bridge.dark ? 0.32 : 0.06)
                border.width: 1
                border.color: Qt.rgba(1, 1, 1, bridge.dark ? 0.08 : 0.40)
            }

            Rectangle {
                id: pill
                z: 1
                y: 6
                x: 4
                width: 96
                height: 36
                radius: 12
                color: "#ff5a1f"
            }
            NumberAnimation { id: slideX; target: pill; property: "x"; duration: 280; easing.type: Easing.OutCubic }
            NumberAnimation { id: slideW; target: pill; property: "width"; duration: 280; easing.type: Easing.OutCubic }

            component NavChip: Item {
                property string label: ""
                property bool hot: false
                signal picked()
                width: 96
                height: 48
                z: 2
                Text {
                    anchors.centerIn: parent
                    text: label
                    color: hot ? "#ffffff" : (bridge.dark ? "#f4f6fa" : "#1c1c1e")
                    font.pixelSize: 13
                    font.bold: hot
                }
                TapHandler { onTapped: picked() }
            }

            NavChip {
                id: libraryChip
                x: 4
                width: 84
                label: "Library"
                hot: bridge.page === "library"
                onPicked: bridge.showPage("library")
            }
            NavChip {
                id: backupsChip
                x: 102
                width: 100
                label: "Backups"
                hot: bridge.page === "backups"
                onPicked: bridge.showPage("backups")
            }
            NavChip {
                id: installChip
                x: 216
                width: 100
                label: "Installer"
                hot: bridge.page === "install"
                onPicked: bridge.showPage("install")
            }
            Item {
                x: 328
                y: 2
                width: 44
                height: 44
                z: 2
                Text {
                    anchors.centerIn: parent
                    text: bridge.glyphHome
                    font.family: bridge.iconFont
                    font.pixelSize: 22
                    color: homeH.hovered ? "#ff5a1f" : (bridge.dark ? "#f4f6fa" : "#1c1c1e")
                }
                HoverHandler { id: homeH }
                TapHandler { onTapped: bridge.goHome() }
            }
            NavChip {
                id: filesChip
                x: 384
                width: 84
                label: "Files"
                hot: bridge.page === "files"
                onPicked: bridge.showPage("files")
            }
            NavChip {
                id: encryptChip
                x: 482
                width: 92
                label: "Encrypt"
                hot: bridge.page === "encrypt"
                onPicked: bridge.showPage("encrypt")
            }
        }
    }

    Item {
        id: loadDialog
        visible: bridge.loadOn && bridge.libraryOn
        anchors.fill: parent
        z: 36
        MouseArea {
            anchors.fill: parent
            hoverEnabled: true
            acceptedButtons: Qt.AllButtons
            onPressed: function (mouse) { mouse.accepted = true }
            onWheel: function (wheel) { wheel.accepted = true }
        }
        GlassPlate {
            width: Math.min(520, parent.width - 80)
            height: loadCol.implicitHeight + 36
            anchors.centerIn: parent
            dark: bridge.dark
            matte: true
            plateRadius: 18
            foot: 10
            Column {
                id: loadCol
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.margins: 18
                spacing: 10
                Row {
                    spacing: 10
                    width: parent.width
                    Item {
                        width: 28
                        height: 28
                        RotationAnimation on rotation {
                            running: loadDialog.visible
                            loops: Animation.Infinite
                            from: 0
                            to: 360
                            duration: 800
                        }
                        Rectangle {
                            anchors.fill: parent
                            radius: 14
                            color: "transparent"
                            border.width: 3
                            border.color: Qt.rgba(1, 0.35, 0.12, 0.25)
                        }
                        Rectangle {
                            width: 8
                            height: 8
                            radius: 4
                            color: "#ff5a1f"
                            anchors.horizontalCenter: parent.horizontalCenter
                            anchors.top: parent.top
                        }
                    }
                    Text {
                        width: parent.width - 38
                        text: "Loading content"
                        color: bridge.dark ? "#f2f4f8" : "#1d1d1f"
                        font.pixelSize: 18
                        font.bold: true
                        anchors.verticalCenter: parent.verticalCenter
                    }
                }
                Text {
                    width: parent.width
                    wrapMode: Text.Wrap
                    text: bridge.loadDetail
                    color: bridge.dark ? "#f4f6fa" : "#1d1d1f"
                    font.pixelSize: 13
                }
                Text {
                    width: parent.width
                    visible: text.length > 0
                    wrapMode: Text.Wrap
                    text: bridge.loadLog
                    color: bridge.dark ? "#9aa3b2" : "#5c6570"
                    font.pixelSize: 12
                }
            }
        }
    }

    Item {
        id: logDialog
        property bool logShown: false
        property bool logClosing: false
        property real veil: 0
        property real cardPop: 0.94
        property real cardLift: 16
        property real cardH: 560
        visible: logShown
        focus: visible
        anchors.fill: parent
        z: 40
        Keys.onEscapePressed: root.taskLogOn = false
        function syncLog() {
            if (root.taskLogOn) {
                var fresh = !logShown || veil < 0.05
                logShown = true
                logClosing = false
                logClose.stop()
                if (fresh) {
                    placeCard()
                    veil = 0
                    cardPop = 0.94
                    cardLift = 16
                }
                logOpen.restart()
                return
            }
            if (!logShown)
                return
            logOpen.stop()
            logClosing = true
            logClose.restart()
        }
        ParallelAnimation {
            id: logOpen
            NumberAnimation { target: logDialog; property: "veil"; to: 1; duration: 180; easing.type: Easing.OutCubic }
            NumberAnimation { target: logDialog; property: "cardPop"; to: 1; duration: 240; easing.type: Easing.OutBack }
            NumberAnimation { target: logDialog; property: "cardLift"; to: 0; duration: 240; easing.type: Easing.OutCubic }
        }
        ParallelAnimation {
            id: logClose
            NumberAnimation { target: logDialog; property: "veil"; to: 0; duration: 160; easing.type: Easing.InCubic }
            NumberAnimation { target: logDialog; property: "cardPop"; to: 0.96; duration: 160; easing.type: Easing.InCubic }
            NumberAnimation { target: logDialog; property: "cardLift"; to: 12; duration: 160; easing.type: Easing.InCubic }
            onFinished: {
                logDialog.logClosing = false
                if (!root.taskLogOn)
                    logDialog.logShown = false
            }
        }
        Shortcut {
            sequences: [StandardKey.Copy]
            enabled: logDialog.visible
            onActivated: bridge.copyText(root.logSelCount() ? root.logSelectedText() : root.logLines(""))
        }
        Shortcut {
            sequences: [StandardKey.SelectAll]
            enabled: logDialog.visible
            onActivated: root.logSelectAll()
        }
        onVisibleChanged: if (visible) placeCard()
        function placeCard() {
            logCard.x = Math.max(12, (width - logCard.width) / 2)
            logCard.y = Math.max(12, (height - logCard.height) / 2)
        }
        Rectangle {
            anchors.fill: parent
            opacity: logDialog.veil
            color: Qt.rgba(0, 0, 0, bridge.dark ? 0.62 : 0.46)
            MouseArea {
                anchors.fill: parent
                hoverEnabled: true
                acceptedButtons: Qt.AllButtons
                onPressed: function (mouse) { mouse.accepted = true }
                onWheel: function (wheel) { wheel.accepted = true }
                onClicked: root.taskLogOn = false
            }
        }
        Repeater {
            model: 4
            delegate: Rectangle {
                required property int index
                property real t: (index + 1) / 4
                property real spread: 16 + t * 28
                x: logCard.x - spread * 0.35
                y: logCard.y + 10 + index * 2
                width: logCard.width + spread * 0.7
                height: logCard.height - 8
                radius: 24 + spread * 0.15
                opacity: logDialog.veil
                color: Qt.rgba(0, 0, 0, 0.28 * (1.05 - t))
            }
        }
        GlassPlate {
            id: logCard
            width: Math.min(920, logDialog.width - 64)
            height: Math.max(280, Math.min(logDialog.cardH, Math.max(280, logDialog.height - 24)))
            opacity: logDialog.veil
            scale: logDialog.cardPop
            transformOrigin: Item.Center
            transform: Translate { y: logDialog.cardLift }
            dark: bridge.dark
            matte: true
            plateRadius: 18
            foot: 10
            Item {
                anchors.fill: parent
                Column {
                    id: logHead
                    anchors.top: parent.top
                    anchors.left: parent.left
                    anchors.right: parent.right
                    spacing: 8
                    Row {
                        width: parent.width
                        spacing: 8
                        Item {
                            width: parent.width - 44
                            height: logTitle.implicitHeight
                            Column {
                                id: logTitle
                                width: parent.width
                                spacing: 2
                                Text {
                                    width: parent.width
                                    text: root.taskLogTitle
                                    color: bridge.dark ? "#f2f4f8" : "#1d1d1f"
                                    font.pixelSize: 16
                                    font.bold: true
                                    elide: Text.ElideRight
                                }
                                Text {
                                    width: parent.width
                                    text: root.taskLogAction
                                    color: "#9aa3b2"
                                    font.pixelSize: 11
                                    elide: Text.ElideRight
                                }
                            }
                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.SizeAllCursor
                                drag.target: logCard
                                drag.axis: Drag.XAndYAxis
                                drag.minimumX: 8
                                drag.maximumX: Math.max(8, logDialog.width - logCard.width - 8)
                                drag.minimumY: 8
                                drag.maximumY: Math.max(8, logDialog.height - logCard.height - 8)
                            }
                        }
                        RaiseButton {
                            width: 32
                            height: 32
                            glyph: bridge.glyphClose
                            fontName: bridge.iconFont
                            tip: "Close"
                            onClicked: root.taskLogOn = false
                        }
                    }
                    Row {
                        spacing: 8
                        Rectangle {
                            radius: 8
                            height: 22
                            width: errCount.implicitWidth + 16
                            color: Qt.rgba(1, 0.3, 0.31, root.logTone === "error" ? 0.55 : 0.22)
                            border.width: root.logTone === "error" ? 1 : 0
                            border.color: "#ff4d4f"
                            Text {
                                id: errCount
                                anchors.centerIn: parent
                                text: root.toneCount("error") + " errors"
                                color: "#ff4d4f"
                                font.pixelSize: 11
                                font.bold: true
                            }
                            TapHandler { onTapped: root.toggleLogTone("error") }
                        }
                        Rectangle {
                            radius: 8
                            height: 22
                            width: warnCount.implicitWidth + 16
                            color: Qt.rgba(0.96, 0.77, 0.26, root.logTone === "warn" ? 0.5 : 0.18)
                            border.width: root.logTone === "warn" ? 1 : 0
                            border.color: "#f5c542"
                            Text {
                                id: warnCount
                                anchors.centerIn: parent
                                text: root.toneCount("warn") + " warnings"
                                color: "#f5c542"
                                font.pixelSize: 11
                                font.bold: true
                            }
                            TapHandler { onTapped: root.toggleLogTone("warn") }
                        }
                        Rectangle {
                            radius: 8
                            height: 22
                            width: okCount.implicitWidth + 16
                            color: Qt.rgba(0.24, 0.86, 0.52, root.logTone === "ok" ? 0.45 : 0.16)
                            border.width: root.logTone === "ok" ? 1 : 0
                            border.color: "#3ddc84"
                            Text {
                                id: okCount
                                anchors.centerIn: parent
                                text: root.toneCount("ok") + " ok"
                                color: "#3ddc84"
                                font.pixelSize: 11
                                font.bold: true
                            }
                            TapHandler { onTapped: root.toggleLogTone("ok") }
                        }
                    }
                    Row {
                        spacing: 6
                        RaiseButton {
                            width: 32
                            height: 32
                            glyph: bridge.glyphCopy
                            fontName: bridge.iconFont
                            ink: "#ff4d4f"
                            tip: "Copy errors"
                            onClicked: bridge.copyText(root.logLines("error"))
                        }
                        RaiseButton {
                            width: 32
                            height: 32
                            glyph: bridge.glyphCopy
                            fontName: bridge.iconFont
                            ink: "#f5c542"
                            tip: "Copy warnings"
                            onClicked: bridge.copyText(root.logLines("warn"))
                        }
                        RaiseButton {
                            width: 32
                            height: 32
                            glyph: bridge.glyphCopy
                            fontName: bridge.iconFont
                            ink: "#3ddc84"
                            tip: "Copy ok lines"
                            onClicked: bridge.copyText(root.logLines("ok"))
                        }
                        RaiseButton {
                            width: 32
                            height: 32
                            glyph: bridge.glyphCopy
                            fontName: bridge.iconFont
                            tip: "Copy all"
                            onClicked: bridge.copyText(root.logLines(""))
                        }
                        RaiseButton {
                            width: 32
                            height: 32
                            glyph: bridge.glyphCopy
                            fontName: bridge.iconFont
                            ink: "#ff5a1f"
                            tip: "Copy selected"
                            enabled: root.logSelCount() > 0
                            onClicked: bridge.copyText(root.logSelectedText())
                        }
                    }
                }
                GlassPlate {
                    anchors.top: logHead.bottom
                    anchors.topMargin: 8
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.bottom: parent.bottom
                    sunk: true
                    dark: bridge.dark
                    plateRadius: 12
                    foot: 4
                    ListView {
                        id: logList
                        anchors.fill: parent
                        anchors.rightMargin: logVBar.width + 4
                        anchors.bottomMargin: logHBar.height
                        clip: true
                        spacing: 2
                        boundsBehavior: Flickable.StopAtBounds
                        flickableDirection: Flickable.HorizontalAndVerticalFlick
                        contentWidth: Math.max(width, root.logMaxW)
                        model: root.logView
                        delegate: Item {
                            required property int index
                            required property var modelData
                            readonly property int srcIndex: modelData.src
                            readonly property bool marked: root.logOn(srcIndex)
                            width: logList.contentWidth
                            height: 20
                            Rectangle {
                                anchors.fill: parent
                                radius: 6
                                color: root.toneFill(modelData.tone)
                                border.width: marked ? 1 : 0
                                border.color: "#ff5a1f"
                            }
                            Rectangle {
                                visible: marked
                                width: 3
                                radius: 2
                                anchors.left: parent.left
                                anchors.leftMargin: 4
                                anchors.top: parent.top
                                anchors.bottom: parent.bottom
                                anchors.topMargin: 5
                                anchors.bottomMargin: 5
                                color: "#ff5a1f"
                            }
                            Text {
                                anchors.left: parent.left
                                anchors.leftMargin: 14
                                anchors.verticalCenter: parent.verticalCenter
                                text: modelData.text
                                color: root.toneColor(modelData.tone)
                                font.pixelSize: 10
                                font.family: "Consolas"
                                wrapMode: Text.NoWrap
                            }
                            MouseArea {
                                anchors.fill: parent
                                onClicked: function (mouse) {
                                    root.logClick(srcIndex, mouse.modifiers)
                                }
                            }
                        }
                    }
                    Rectangle {
                        id: logVBar
                        visible: logList.contentHeight > logList.height + 4
                        width: visible ? 8 : 0
                        radius: 4
                        color: Qt.rgba(1, 1, 1, bridge.dark ? 0.08 : 0.35)
                        anchors.right: parent.right
                        anchors.top: parent.top
                        anchors.bottom: logHBar.top
                        anchors.bottomMargin: 4
                        Rectangle {
                            id: logVThumb
                            width: parent.width
                            radius: 4
                            color: "#ff5a1f"
                            height: Math.max(28, logList.visibleArea.heightRatio * Math.max(0, logVBar.height))
                            Binding on y {
                                when: !logVDrag.drag.active
                                value: logList.visibleArea.yPosition * Math.max(0, logVBar.height - height)
                            }
                            MouseArea {
                                id: logVDrag
                                anchors.fill: parent
                                anchors.margins: -6
                                drag.target: logVThumb
                                drag.axis: Drag.YAxis
                                drag.minimumY: 0
                                drag.maximumY: Math.max(0, logVBar.height - logVThumb.height)
                                onPositionChanged: {
                                    if (!drag.active)
                                        return
                                    var travel = logVBar.height - logVThumb.height
                                    var frac = travel <= 1 ? 0 : logVThumb.y / travel
                                    logList.contentY = frac * Math.max(0, logList.contentHeight - logList.height)
                                }
                            }
                        }
                    }
                    Rectangle {
                        id: logHBar
                        visible: logList.contentWidth > logList.width + 4
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.bottom: parent.bottom
                        height: visible ? 8 : 0
                        radius: 4
                        color: Qt.rgba(1, 1, 1, bridge.dark ? 0.08 : 0.35)
                        Rectangle {
                            id: logThumb
                            height: parent.height
                            radius: 4
                            color: "#ff5a1f"
                            width: Math.max(28, logList.visibleArea.widthRatio * logHBar.width)
                            Binding on x {
                                when: !logDrag.drag.active
                                value: logList.visibleArea.xPosition * Math.max(0, logHBar.width - width)
                            }
                            MouseArea {
                                id: logDrag
                                anchors.fill: parent
                                anchors.margins: -6
                                preventStealing: true
                                drag.target: logThumb
                                drag.axis: Drag.XAxis
                                drag.minimumX: 0
                                drag.maximumX: Math.max(0, logHBar.width - logThumb.width)
                                onPositionChanged: {
                                    if (!drag.active)
                                        return
                                    var travel = logHBar.width - logThumb.width
                                    var frac = travel <= 1 ? 0 : logThumb.x / travel
                                    logList.contentX = frac * Math.max(0, logList.contentWidth - logList.width)
                                }
                            }
                        }
                    }
                }
            }
            MouseArea {
                z: 4
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.bottom: parent.bottom
                width: 96
                height: 18
                hoverEnabled: true
                cursorShape: Qt.SizeVerCursor
                preventStealing: true
                property real originH: 0
                property real originY: 0
                onPressed: function (mouse) {
                    originH = logDialog.cardH
                    originY = mapToItem(logDialog, 0, mouse.y).y
                }
                onPositionChanged: function (mouse) {
                    if (!pressed)
                        return
                    var y = mapToItem(logDialog, 0, mouse.y).y
                    var maxH = Math.max(280, logDialog.height - logCard.y - 12)
                    logDialog.cardH = Math.max(280, Math.min(maxH, originH + (y - originY)))
                }
                Rectangle {
                    width: 36
                    height: 4
                    radius: 2
                    anchors.centerIn: parent
                    color: Qt.rgba(1, 1, 1, bridge.dark ? 0.38 : 0.5)
                }
            }
        }
    }

    property string _selected: ""
}
