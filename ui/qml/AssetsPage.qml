import QtQuick

// Assets Tools stage. Center chrome is QML. Tables, editors, and canvases stay widgets in the well.
// Packages queue stays a widget in the sidebar well. This page paints depth + nav.
Item {
    id: root

    Chrome { id: chrome }

    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            GradientStop { position: 0.0; color: bridge.dark ? "#1a2230" : "#eef1f6" }
            GradientStop { position: 1.0; color: bridge.dark ? "#161b24" : "#d5dbe3" }
        }
    }

    Item {
        id: stage
        property bool layoutDrag: false
        property real sideLive: 380
        property real dockLive: 560
        property bool dockUser: false
        property real holdCenter: 0
        property real holdDock: 0
        property real footHold: 0
        // Packages viewer opens level with the Finder (the first layout). Texmesh keeps its own dock width.
        function dockCap() {
            return Math.max(280, Math.round((width - sideLive - 20) / 2))
        }
        function fitDock() {
            if (bridge.suite === "texmesh" || !bridge.viewerOn)
                return
            var cap = dockCap()
            var next = dockUser ? Math.min(dockLive, cap) : cap
            if (Math.abs(next - dockLive) < 1)
                return
            dockLive = next
        }
        function sideFoot() {
            if (layoutDrag)
                return footHold
            var o = side.mapToItem(root, 0, 0)
            if (o.x + side.width <= nav.x + 8 || o.x >= nav.x + nav.width - 8)
                return 0
            return chrome.contentInset(nav.height)
        }
        function beginDrag() {
            holdCenter = centerSlot.width
            holdDock = dockSlot.width
            footHold = side.footPad
            layoutDrag = true
        }
        function endDrag() {
            layoutDrag = false
            bridge.setSideW(sideLive)
            sideLive = bridge.sideW
            if (bridge.suite !== "texmesh" && bridge.viewerOn)
                fitDock()
            bridge.setDockW(dockLive)
            if (bridge.suite === "texmesh" || !bridge.viewerOn)
                dockLive = bridge.dockW
            queueSlot.sync()
            dockSlot.sync()
            previewSlot.sync()
            formToolSlot.sync()
            centerBody.sync()
            centerChrome.syncWells()
        }
        Component.onCompleted: {
            sideLive = bridge.sideW
            fitDock()
        }
        onWidthChanged: fitDock()
        Connections {
            target: bridge
            function onLayoutChanged() {
                if (stage.layoutDrag)
                    return
                stage.sideLive = bridge.sideW
                if (bridge.suite === "texmesh" || !bridge.viewerOn)
                    stage.dockLive = bridge.dockW
                else
                    stage.fitDock()
            }
            function onChanged() {
                if (stage.layoutDrag)
                    return
                stage.fitDock()
            }
        }
        anchors.fill: parent
        anchors.leftMargin: 10
        anchors.rightMargin: 10
        anchors.topMargin: 8
        anchors.bottomMargin: chrome.stageMargin

        AssetsSide {
            id: side
            quiet: stage.layoutDrag || dockEase.running
            freeze: stage.layoutDrag
            anchors.left: parent.left
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            width: stage.sideLive
            footPad: stage.sideFoot()
        }

        Item {
            id: queueSlot
            anchors.left: side.left
            anchors.right: side.right
            anchors.top: side.top
            anchors.bottom: side.bottom
            anchors.leftMargin: 16
            anchors.rightMargin: 16
            anchors.topMargin: side.headH
            anchors.bottomMargin: side.footH + side.footPad
            visible: bridge.showQueue

            function sync() {
                if (stage.layoutDrag)
                    return
                if (!bridge.showQueue || width < 8 || height < 8) {
                    bridge.placeQueue(0, 0, 0, 0)
                    return
                }
                var p = mapToItem(root, 0, 0)
                bridge.placeQueue(p.x, p.y, width, height)
            }
            onXChanged: sync()
            onYChanged: sync()
            onWidthChanged: sync()
            onHeightChanged: sync()
            Component.onCompleted: sync()
        }

        Item {
            id: dockSlot
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            width: bridge.dockOn ? (bridge.viewerExpanded ? parent.width - stage.sideLive - 8 : stage.dockLive) : 0
            readonly property real contentW: stage.layoutDrag ? stage.holdDock : width
            clip: true
            property bool widthReady: false
            Behavior on width {
                id: dockEase
                enabled: dockSlot.widthReady && !stage.layoutDrag
                NumberAnimation { duration: 180; easing.type: Easing.OutCubic }
            }

            AssetsViewer {
                id: viewerChrome
                quiet: stage.layoutDrag || dockEase.running
                freeze: stage.layoutDrag
                anchors.left: parent.left
                anchors.top: parent.top
                anchors.bottom: parent.bottom
                width: dockSlot.contentW
                visible: bridge.viewerOn && dockSlot.width > 40
            }

            AssetsDock {
                id: formChrome
                quiet: stage.layoutDrag || dockEase.running
                freeze: stage.layoutDrag
                anchors.left: parent.left
                anchors.top: parent.top
                anchors.bottom: parent.bottom
                width: dockSlot.contentW
                visible: bridge.formOn && dockSlot.width > 40
            }

            GlassPlate {
                anchors.left: parent.left
                anchors.top: parent.top
                anchors.bottom: parent.bottom
                width: dockSlot.contentW
                visible: !bridge.viewerOn && !bridge.formOn && dockSlot.width > 40
                dark: bridge.dark
                quiet: stage.layoutDrag || dockEase.running
                freeze: stage.layoutDrag
                plateRadius: 16
                foot: 8
            }

            Item {
                id: previewSlot
                anchors.left: parent.left
                anchors.top: parent.top
                anchors.bottom: parent.bottom
                anchors.leftMargin: 16
                anchors.topMargin: viewerChrome.padTop
                anchors.bottomMargin: viewerChrome.padBottom
                width: Math.max(0, dockSlot.contentW - 32)
                visible: bridge.viewerOn && dockSlot.width > 40

                Rectangle {
                    anchors.fill: parent
                    radius: 11
                    color: bridge.dark ? "#101319" : "#e2e6ec"
                    border.width: 1
                    border.color: bridge.dark ? "#050608" : "#aeb5c0"
                }
                Rectangle {
                    anchors.fill: parent
                    anchors.margins: 2
                    radius: 9
                    color: "transparent"
                    border.width: 1
                    border.color: bridge.dark ? "#2a303a" : "#ffffff"
                }
                Rectangle {
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.margins: 2
                    height: 5
                    radius: 8
                    gradient: Gradient {
                        GradientStop { position: 0.0; color: Qt.rgba(0, 0, 0, 0.42) }
                        GradientStop { position: 1.0; color: "transparent" }
                    }
                }

                Flickable {
                    visible: !bridge.viewEditor && bridge.previewImage.length === 0 && !bridge.previewAudio
                    anchors.fill: parent
                    anchors.margins: 10
                    contentWidth: viewerText.implicitWidth
                    contentHeight: viewerText.implicitHeight
                    clip: true
                    TextEdit {
                        id: viewerText
                        width: Math.max(implicitWidth, 40)
                        readOnly: true
                        selectByMouse: true
                        wrapMode: TextEdit.NoWrap
                        textFormat: bridge.previewRich ? TextEdit.RichText : TextEdit.PlainText
                        color: bridge.previewRich ? "#d4d4d4" : (bridge.dark ? "#f2f4f8" : "#1d1d1f")
                        font.family: "Consolas"
                        font.pixelSize: bridge.previewPt + 2
                        text: bridge.previewOn ? bridge.previewBody : bridge.viewHint
                    }
                }

                Image {
                    visible: bridge.viewPane === 0 && bridge.previewImage.length > 0
                    anchors.fill: parent
                    anchors.margins: 12
                    source: bridge.previewImage
                    fillMode: Image.PreserveAspectFit
                    asynchronous: true
                    smooth: true
                    mipmap: true
                }

                Column {
                    visible: bridge.viewPane === 0 && bridge.previewAudio
                    anchors.centerIn: parent
                    width: Math.min(parent.width - 40, 320)
                    spacing: 14
                    Text {
                        width: parent.width
                        horizontalAlignment: Text.AlignHCenter
                        wrapMode: Text.WordWrap
                        text: (typeof bridge.previewBody === "string" ? qsTr(bridge.previewBody) : bridge.previewBody)
                        color: bridge.dark ? "#f2f4f8" : "#1d1d1f"
                        font.pixelSize: 13
                    }
                    Row {
                        anchors.horizontalCenter: parent.horizontalCenter
                        spacing: 8
                        RaiseButton {
                            width: 88
                            height: 36
                            label: qsTr("Play")
                            accent: true
                            onClicked: bridge.audioPlay()
                        }
                        RaiseButton {
                            width: 88
                            height: 36
                            label: qsTr("Stop")
                            onClicked: bridge.audioStop()
                        }
                    }
                }

                Flickable {
                    id: editorFlick
                    visible: bridge.viewEditor
                    anchors.top: parent.top
                    anchors.bottom: parent.bottom
                    anchors.left: editorGutter.right
                    anchors.right: parent.right
                    anchors.margins: 10
                    anchors.leftMargin: 6
                    contentWidth: editorText.implicitWidth
                    contentHeight: editorText.implicitHeight
                    clip: true
                    TextEdit {
                        id: editorText
                        width: Math.max(implicitWidth, 40)
                        readOnly: bridge.viewPane === 0 // Viewer = same render as Editor, just locked
                        selectByMouse: true
                        wrapMode: TextEdit.NoWrap
                        textFormat: TextEdit.PlainText
                        color: bridge.dark ? "#f2f4f8" : "#1d1d1f"
                        selectionColor: "#ff5a1f"
                        font.family: "Consolas"
                        font.pixelSize: bridge.previewPt + 2
                        text: bridge.previewPlain
                        onTextChanged: if (bridge.viewPane === 1) bridge.setPreviewText(text)
                        Keys.onPressed: function (event) {
                            if (event.key === Qt.Key_S && (event.modifiers & Qt.ControlModifier) && !(event.modifiers & Qt.ShiftModifier)) {
                                bridge.viewerSave()
                                event.accepted = true
                            }
                        }
                        Component.onCompleted: bridge.attachEditor(textDocument)
                    }
                }

                FontMetrics {
                    id: editorMetrics
                    font.family: "Consolas"
                    font.pixelSize: bridge.previewPt + 2
                }
                Item {
                    id: editorGutter
                    visible: bridge.viewEditor
                    anchors.left: parent.left
                    anchors.top: parent.top
                    anchors.bottom: parent.bottom
                    anchors.leftMargin: 3
                    anchors.topMargin: 3
                    anchors.bottomMargin: 3
                    width: 46
                    clip: true
                    Rectangle {
                        anchors.fill: parent
                        color: bridge.dark ? "#0b0d11" : "#d4d9e1"
                        Rectangle {
                            anchors.right: parent.right
                            anchors.top: parent.top
                            anchors.bottom: parent.bottom
                            width: 1
                            color: bridge.dark ? "#303640" : "#aeb5c0"
                        }
                    }
                    // ponytail: only the lines in view. A full-file column reflows every splitter pixel.
                    Item {
                        id: gutterLines
                        anchors.fill: parent
                        property real lineH: Math.max(1, editorMetrics.lineSpacing)
                        property int firstLine: Math.max(0, Math.floor(Math.max(0, editorFlick.contentY - 10) / lineH))
                        property int shownLines: Math.min(
                            Math.max(0, editorText.lineCount - firstLine),
                            Math.ceil(height / lineH) + 2)
                        Repeater {
                            model: gutterLines.shownLines
                            Text {
                                required property int index
                                x: 0
                                y: 10 + (gutterLines.firstLine + index) * gutterLines.lineH - editorFlick.contentY
                                width: editorGutter.width - 7
                                height: gutterLines.lineH
                                horizontalAlignment: Text.AlignRight
                                verticalAlignment: Text.AlignVCenter
                                text: gutterLines.firstLine + index + 1
                                color: "#858585"
                                font.family: "Consolas"
                                font.pixelSize: bridge.previewPt
                            }
                        }
                    }
                }

                function sync() {
                    if (stage.layoutDrag)
                        return
                    if (!visible || width < 8 || height < 8) {
                        bridge.placePreview(0, 0, 0, 0)
                        return
                    }
                    var p = mapToItem(root, 0, 0)
                    bridge.placePreview(p.x, p.y, width, height)
                }
                onXChanged: sync()
                onYChanged: sync()
                onWidthChanged: sync()
                onHeightChanged: sync()
                Component.onCompleted: sync()
            }

            Item {
                id: formToolSlot
                anchors.left: parent.left
                anchors.bottom: parent.bottom
                anchors.top: parent.top
                anchors.leftMargin: 16
                anchors.bottomMargin: 16
                anchors.topMargin: formChrome.padTop
                width: Math.max(0, dockSlot.contentW - 32)
                visible: bridge.formTool && dockSlot.width > 40

                function sync() {
                    if (stage.layoutDrag)
                        return
                    if (!visible || width < 8 || height < 8) {
                        bridge.placeFormTool(0, 0, 0, 0)
                        return
                    }
                    var p = mapToItem(root, 0, 0)
                    bridge.placeFormTool(p.x, p.y, width, height)
                }
                onXChanged: sync()
                onYChanged: sync()
                onWidthChanged: sync()
                onHeightChanged: sync()
                Component.onCompleted: sync()
            }

            function contentH() {
                if (width < 40)
                    return height
                var o = mapToItem(root, 0, 0)
                if (o.x + width <= nav.x + 8 || o.x >= nav.x + nav.width - 8)
                    return height
                return Math.max(40, height - chrome.contentInset(nav.height))
            }

            function sync() {
                if (stage.layoutDrag)
                    return
                var p = mapToItem(root, 0, 0)
                bridge.placeDock(p.x, p.y, width, contentH())
            }
            onXChanged: sync()
            onYChanged: sync()
            onWidthChanged: sync()
            onHeightChanged: sync()
            Component.onCompleted: {
                widthReady = true
                sync()
            }
        }

        Item {
            id: centerSlot
            visible: !bridge.viewerExpanded
            anchors.left: side.right
            anchors.leftMargin: 8
            anchors.right: dockSlot.left
            anchors.rightMargin: dockSlot.width > 8 ? 12 : 0
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            anchors.bottomMargin: chrome.contentInset(nav.height)
            readonly property real contentW: stage.layoutDrag ? stage.holdCenter : width
            clip: true

            AssetsCenter {
                id: centerChrome
                quiet: stage.layoutDrag || dockEase.running
                freeze: stage.layoutDrag
                anchors.left: parent.left
                anchors.top: parent.top
                anchors.bottom: parent.bottom
                width: centerSlot.contentW
            }

            Item {
                id: centerBody
                visible: bridge.centerKind === "page"
                anchors.left: parent.left
                anchors.top: parent.top
                anchors.bottom: parent.bottom
                anchors.leftMargin: centerChrome.padSide
                anchors.topMargin: centerChrome.padTop
                anchors.bottomMargin: centerChrome.padBottom
                width: Math.max(40, centerSlot.contentW - centerChrome.padSide * 2)

                property var finderRows: []
                property var crumbRows: []
                property real finderTypeWidth: 105
                property real finderSizeWidth: 82
                property real finderModifiedWidth: 132
                function parseFinder() {
                    try { return JSON.parse(bridge.finderJson) }
                    catch (e) { return [] }
                }
                function parseCrumbs() {
                    try { return JSON.parse(bridge.crumbsJson) }
                    catch (e) { return [] }
                }
                Connections {
                    target: bridge
                    function onChanged() {
                        centerBody.finderRows = centerBody.parseFinder()
                        centerBody.crumbRows = centerBody.parseCrumbs()
                    }
                    function onFinderChanged() {
                        centerBody.finderRows = centerBody.parseFinder()
                    }
                }
                Component.onCompleted: {
                    finderRows = parseFinder()
                    crumbRows = parseCrumbs()
                    sync()
                }

                Column {
                    anchors.fill: parent
                    visible: bridge.suite !== "texmesh"
                    spacing: 8

                    Item {
                        id: finderBox
                        visible: bridge.page === "packages"
                        width: parent.width
                        height: parent.height
                        Rectangle {
                            anchors.fill: parent
                            radius: 12
                            color: Qt.rgba(0, 0, 0, bridge.dark ? 0.28 : 0.06)
                            border.width: 1
                            border.color: Qt.rgba(1, 1, 1, bridge.dark ? 0.10 : 0.40)
                        }
                        Item {
                            anchors.fill: parent
                            anchors.margins: 12

                            Item {
                                id: finderHead
                                anchors.top: parent.top
                                anchors.left: parent.left
                                anchors.right: parent.right
                                height: 18
                                Text {
                                    anchors.left: parent.left
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: qsTr("Finder")
                                    color: bridge.dark ? "#f2f4f8" : "#1d1d1f"
                                    font.pixelSize: 13
                                    font.bold: true
                                }
                                Text {
                                    anchors.right: parent.right
                                    anchors.verticalCenter: parent.verticalCenter
                                    width: parent.width * 0.62
                                    horizontalAlignment: Text.AlignRight
                                    text: (typeof bridge.finderMeta === "string" ? qsTr(bridge.finderMeta) : bridge.finderMeta)
                                    color: bridge.dark ? "#8b93a1" : "#5c6570"
                                    font.pixelSize: 12
                                    elide: Text.ElideLeft
                                }
                            }

                            Flickable {
                                id: crumbFlick
                                anchors.top: finderHead.bottom
                                anchors.topMargin: 8
                                anchors.left: parent.left
                                anchors.right: parent.right
                                height: 32
                                contentWidth: crumbRow.width
                                contentHeight: height
                                clip: true
                                flickableDirection: Flickable.HorizontalFlick
                                Rectangle {
                                    anchors.fill: parent
                                    radius: 8
                                    color: Qt.rgba(0, 0, 0, bridge.dark ? 0.22 : 0.05)
                                }
                                Row {
                                    id: crumbRow
                                    height: 32
                                    spacing: 4
                                    leftPadding: 6
                                    Repeater {
                                        model: centerBody.crumbRows
                                        delegate: Row {
                                            required property var modelData
                                            required property int index
                                            height: 32
                                            spacing: 4
                                            Text {
                                                visible: index > 0
                                                text: qsTr("\u203a")
                                                color: bridge.dark ? "#8b93a1" : "#5c6570"
                                                font.pixelSize: 14
                                                anchors.verticalCenter: parent.verticalCenter
                                            }
                                            Rectangle {
                                                width: crumbLab.implicitWidth + 16
                                                height: 24
                                                radius: 8
                                                anchors.verticalCenter: parent.verticalCenter
                                                color: modelData.hot ? "#ff5a1f" : Qt.rgba(1, 0.35, 0.12, bridge.dark ? 0.45 : 0.28)
                                                Text {
                                                    id: crumbLab
                                                    anchors.centerIn: parent
                                                    text: (modelData.label || "").length > 28 ? modelData.label.slice(0, 26) + qsTr("\u2026") : (modelData.label || "")
                                                    color: "#ffffff"
                                                    font.pixelSize: 11
                                                    font.bold: true
                                                }
                                                TapHandler {
                                                    enabled: modelData.depth >= 0
                                                    onTapped: bridge.jumpCrumb(modelData.depth)
                                                }
                                            }
                                        }
                                    }
                                }
                            }

                            Row {
                                id: searchRow
                                anchors.top: crumbFlick.bottom
                                anchors.topMargin: 8
                                anchors.left: parent.left
                                anchors.right: parent.right
                                height: 32
                                spacing: 6
                                RaiseButton {
                                    width: 34
                                    height: 32
                                    label: qsTr("\u2190")
                                    enabled: bridge.finderUpOn
                                    onClicked: bridge.finderUp()
                                }
                                Rectangle {
                                    width: parent.width - 34 - 52 - 12
                                    height: 32
                                    radius: 8
                                    color: Qt.rgba(0, 0, 0, bridge.dark ? 0.38 : 0.08)
                                    TextInput {
                                        anchors.fill: parent
                                        anchors.margins: 8
                                        color: bridge.dark ? "#f2f4f8" : "#1d1d1f"
                                        font.pixelSize: 12
                                        clip: true
                                        Text {
                                            anchors.fill: parent
                                            visible: parent.text.length === 0
                                            text: qsTr("Search this list\u2026")
                                            color: bridge.dark ? "#8b93a1" : "#5c6570"
                                            font.pixelSize: 12
                                            verticalAlignment: Text.AlignVCenter
                                        }
                                        onTextChanged: bridge.setFinderQuery(text)
                                    }
                                }
                                RaiseButton {
                                    width: 52
                                    height: 32
                                    label: qsTr(".fbx")
                                    accent: bridge.finderFbx
                                    onClicked: bridge.toggleFbx()
                                }
                            }

                            Rectangle {
                                id: finderHeader
                                anchors.top: searchRow.bottom
                                anchors.topMargin: 8
                                anchors.left: parent.left
                                anchors.right: parent.right
                                height: 30
                                radius: 7
                                color: Qt.rgba(0, 0, 0, bridge.dark ? 0.28 : 0.07)

                                property real nameWidth: Math.max(150, width - centerBody.finderTypeWidth - centerBody.finderSizeWidth - centerBody.finderModifiedWidth)
                                Row {
                                    anchors.fill: parent
                                    Repeater {
                                        model: [
                                            { title: "Name", key: "name", width: finderHeader.nameWidth },
                                            { title: "Type", key: "type", width: centerBody.finderTypeWidth },
                                            { title: "Size", key: "size", width: centerBody.finderSizeWidth },
                                            { title: "Date modified", key: "modified", width: centerBody.finderModifiedWidth }
                                        ]
                                        delegate: Item {
                                            required property var modelData
                                            width: modelData.width
                                            height: finderHeader.height
                                            Text {
                                                anchors.fill: parent
                                                anchors.leftMargin: 10
                                                anchors.rightMargin: 6
                                                verticalAlignment: Text.AlignVCenter
                                                horizontalAlignment: modelData.key === "size" ? Text.AlignRight : Text.AlignLeft
                                                text: {
                                                    var title = (typeof modelData.title === "string" ? qsTr(modelData.title) : modelData.title)
                                                    if (bridge.finderSort !== modelData.key)
                                                        return title
                                                    return title + (bridge.finderSortAsc ? "  \u2191" : "  \u2193")
                                                }
                                                color: bridge.dark ? "#b8bec8" : "#4d5662"
                                                font.pixelSize: 10
                                                font.bold: true
                                            }
                                            TapHandler { onTapped: bridge.setFinderSort(modelData.key) }
                                        }
                                    }
                                }
                                Rectangle {
                                    x: finderHeader.nameWidth - 2
                                    width: 5; height: parent.height; color: "transparent"
                                    property real startWidth: centerBody.finderTypeWidth
                                    HoverHandler { cursorShape: Qt.SplitHCursor }
                                    DragHandler {
                                        xAxis.enabled: true; yAxis.enabled: false
                                        onActiveChanged: if (active) parent.startWidth = centerBody.finderTypeWidth
                                        onTranslationChanged: centerBody.finderTypeWidth = Math.max(70, parent.startWidth - translation.x)
                                    }
                                }
                                Rectangle {
                                    x: finderHeader.nameWidth + centerBody.finderTypeWidth - 2
                                    width: 5; height: parent.height; color: "transparent"
                                    property real startWidth: centerBody.finderTypeWidth
                                    HoverHandler { cursorShape: Qt.SplitHCursor }
                                    DragHandler {
                                        xAxis.enabled: true; yAxis.enabled: false
                                        onActiveChanged: if (active) parent.startWidth = centerBody.finderTypeWidth
                                        onTranslationChanged: centerBody.finderTypeWidth = Math.max(70, parent.startWidth + translation.x)
                                    }
                                }
                                Rectangle {
                                    x: finderHeader.width - centerBody.finderModifiedWidth - 2
                                    width: 5; height: parent.height; color: "transparent"
                                    property real startWidth: centerBody.finderModifiedWidth
                                    HoverHandler { cursorShape: Qt.SplitHCursor }
                                    DragHandler {
                                        xAxis.enabled: true; yAxis.enabled: false
                                        onActiveChanged: if (active) parent.startWidth = centerBody.finderModifiedWidth
                                        onTranslationChanged: centerBody.finderModifiedWidth = Math.max(105, parent.startWidth - translation.x)
                                    }
                                }
                            }

                            ListView {
                                id: finderList
                                anchors.top: finderHeader.bottom
                                anchors.topMargin: 4
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.bottom: openFolderBtn.top
                                anchors.bottomMargin: 8
                                clip: true
                                spacing: 0
                                reuseItems: true
                                boundsBehavior: Flickable.StopAtBounds
                                model: centerBody.finderRows
                                section.property: "group"
                                section.criteria: ViewSection.FullString
                                section.delegate: Item {
                                    required property string section
                                    width: finderList.width
                                    height: section.length === 0 ? 0 : 22
                                    visible: section.length > 0
                                    Text {
                                        anchors.left: parent.left
                                        anchors.leftMargin: 8
                                        anchors.bottom: parent.bottom
                                        anchors.bottomMargin: 2
                                        text: (typeof section === "string" ? qsTr(section) : section)
                                        color: bridge.dark ? "#8b93a1" : "#5c6570"
                                        font.pixelSize: 11
                                        font.bold: true
                                    }
                                }
                                delegate: Item {
                                    required property var modelData
                                    width: finderList.width
                                    height: 32
                                    HoverHandler { id: rowHover }

                                    Rectangle {
                                        anchors.fill: parent
                                        anchors.leftMargin: 4
                                        anchors.rightMargin: 4
                                        anchors.topMargin: 1
                                        anchors.bottomMargin: 1
                                        radius: 6
                                        visible: modelData.dirty && !modelData.on
                                        color: Qt.rgba(1, 0.62, 0.04, bridge.dark ? 0.22 : 0.38)
                                    }
                                    Rectangle {
                                        anchors.fill: parent
                                        anchors.leftMargin: 4
                                        anchors.rightMargin: 4
                                        anchors.topMargin: 1
                                        anchors.bottomMargin: 1
                                        radius: 6
                                        visible: modelData.on || rowHover.hovered
                                        color: modelData.on ? "#0a84ff" : Qt.rgba(1, 1, 1, bridge.dark ? 0.06 : 0.45)
                                    }
                                    Row {
                                        z: 2
                                        anchors.fill: parent
                                        Item {
                                            width: finderHeader.nameWidth
                                            height: parent.height
                                            Item {
                                                x: 10
                                                width: 26
                                                height: 22
                                                anchors.verticalCenter: parent.verticalCenter
                                                visible: modelData.kind === "dir" || modelData.kind === "asset"
                                                Rectangle {
                                                    x: 1
                                                    y: 1
                                                    width: 12
                                                    height: 6
                                                    radius: 2
                                                    color: modelData.on ? "#d6ebff" : "#8ec8ff"
                                                }
                                                Rectangle {
                                                    x: 0
                                                    y: 5
                                                    width: 26
                                                    height: 16
                                                    radius: 3
                                                    color: modelData.on ? "#f4f8ff" : "#3b9dff"
                                                    Rectangle {
                                                        anchors.left: parent.left
                                                        anchors.right: parent.right
                                                        anchors.top: parent.top
                                                        anchors.margins: 1
                                                        height: 5
                                                        radius: 2
                                                        color: Qt.rgba(1, 1, 1, modelData.on ? 0.55 : 0.28)
                                                    }
                                                }
                                            }
                                            Item {
                                                x: 10
                                                width: 26
                                                height: 22
                                                anchors.verticalCenter: parent.verticalCenter
                                                visible: modelData.kind !== "dir" && modelData.kind !== "asset"
                                                Rectangle {
                                                    x: 6
                                                    y: 0
                                                    width: 16
                                                    height: 21
                                                    radius: 2
                                                    color: modelData.on ? "#ffffff" : (bridge.dark ? "#e8eaed" : "#ffffff")
                                                    border.width: 1
                                                    border.color: modelData.on ? Qt.rgba(1, 1, 1, 0.65) : "#c5c9d1"
                                                }
                                                Rectangle {
                                                    x: 15
                                                    y: 0
                                                    width: 7
                                                    height: 7
                                                    color: modelData.color || "#8e8e93"
                                                }
                                                Rectangle {
                                                    x: 9
                                                    y: 12
                                                    width: 10
                                                    height: 2
                                                    radius: 1
                                                    color: modelData.on ? "#0a84ff" : (modelData.color || "#8e8e93")
                                                }
                                            }
                                            Text {
                                                x: 42
                                                width: parent.width - 50
                                                anchors.verticalCenter: parent.verticalCenter
                                                text: (typeof modelData.name === "string" ? qsTr(modelData.name) : modelData.name) + (modelData.dirty ? " *" : "")
                                                color: modelData.on ? "#ffffff" : (modelData.dirty ? "#ff9f0a" : (bridge.dark ? "#f2f4f8" : "#1d1d1f"))
                                                font.pixelSize: 12
                                                elide: Text.ElideRight
                                            }
                                        }
                                        Text {
                                            width: centerBody.finderTypeWidth
                                            anchors.verticalCenter: parent.verticalCenter
                                            text: modelData.type || ""
                                            color: modelData.on ? "#ffffff" : (bridge.dark ? "#b8bec8" : "#4d5662")
                                            font.pixelSize: 10
                                            elide: Text.ElideRight
                                        }
                                        Text {
                                            width: centerBody.finderSizeWidth
                                            anchors.verticalCenter: parent.verticalCenter
                                            horizontalAlignment: Text.AlignRight
                                            text: (typeof modelData.size === "string" ? qsTr(modelData.size) : modelData.size)
                                            color: modelData.on ? "#ffffff" : "#98989d"
                                            font.pixelSize: 11
                                        }
                                        Text {
                                            width: centerBody.finderModifiedWidth
                                            anchors.verticalCenter: parent.verticalCenter
                                            leftPadding: 12
                                            text: modelData.modified || qsTr("\u2014")
                                            color: modelData.on ? "#ffffff" : "#98989d"
                                            font.pixelSize: 10
                                            elide: Text.ElideRight
                                        }
                                    }
                                    TapHandler {
                                        onTapped: bridge.pickFinder(modelData.row)
                                        onDoubleTapped: bridge.openFinder(modelData.row)
                                    }
                                }
                            }
                            Text {
                                anchors.centerIn: finderList
                                visible: finderList.count === 0
                                width: finderList.width - 24
                                horizontalAlignment: Text.AlignHCenter
                                wrapMode: Text.WordWrap
                                text: qsTr("Finder is empty. Drop a CDP on the left queue.")
                                color: bridge.dark ? "#8b93a1" : "#5c6570"
                                font.pixelSize: 13
                            }
                            RaiseButton {
                                id: openFolderBtn
                                anchors.left: parent.left
                                anchors.bottom: parent.bottom
                                width: 140
                                height: 36
                                label: qsTr("Open folder\u2026")
                                accent: true
                                onClicked: bridge.openFolder()
                            }
                        }
                    }

                    Item {
                        id: configPane
                        visible: bridge.page === "config"
                        width: parent.width
                        height: parent.height - 8
                        property var configModel: {
                            try { return JSON.parse(bridge.configRows) }
                            catch (e) { return [] }
                        }
                        property var menuCell: null
                        property string menuQuery: ""
                        function openMenu(cell) {
                            menuQuery = ""
                            menuCell = cell
                        }
                        function menuHits() {
                            if (!menuCell || !menuCell.options)
                                return []
                            var q = menuQuery.toLowerCase()
                            var out = []
                            for (var i = 0; i < menuCell.options.length; ++i) {
                                var row = menuCell.options[i]
                                var code = (row.code || "").toLowerCase()
                                var label = (row.label || "").toLowerCase()
                                if (q.length && code.indexOf(q) < 0 && label.indexOf(q) < 0)
                                    continue
                                out.push(row)
                            }
                            return out
                        }
                        function menuHas(code) {
                            if (!menuCell)
                                return false
                            var parts = (menuCell.raw || "").split(";")
                            var want = parseFloat(code)
                            for (var i = 0; i < parts.length; ++i) {
                                if (parts[i] === code)
                                    return true
                                var got = parseFloat(parts[i])
                                if (!isNaN(want) && !isNaN(got) && Math.abs(want - got) < 0.001)
                                    return true
                            }
                            return false
                        }
                        function menuPick(code) {
                            if (!menuCell)
                                return
                            if (menuCell.multi) {
                                var parts = []
                                var raw = (menuCell.raw || "").split(";")
                                var found = false
                                for (var i = 0; i < raw.length; ++i) {
                                    if (!raw[i].length)
                                        continue
                                    if (raw[i] === code)
                                        found = true
                                    else
                                        parts.push(raw[i])
                                }
                                if (!found)
                                    parts.push(code)
                                var next = parts.join(";")
                                menuCell = Object.assign({}, menuCell, { raw: next })
                                bridge.configSet(menuCell.index, next)
                            } else {
                                bridge.configSet(menuCell.index, code)
                                menuCell = null
                            }
                        }
                        Rectangle {
                            anchors.fill: parent
                            radius: 12
                            color: Qt.rgba(0, 0, 0, bridge.dark ? 0.38 : 0.08)
                            border.width: 1
                            border.color: Qt.rgba(1, 1, 1, bridge.dark ? 0.12 : 0.40)
                        }
                        DropArea {
                            anchors.fill: parent
                            onDropped: function(drop) {
                                var urls = []
                                for (var i = 0; i < drop.urls.length; ++i)
                                    urls.push(drop.urls[i])
                                bridge.dropConfig(urls)
                            }
                        }
                        Row {
                            id: configBar
                            x: 10
                            y: 8
                            width: parent.width - 20
                            height: 28
                            spacing: 8
                            Text {
                                width: 52
                                height: 28
                                verticalAlignment: Text.AlignVCenter
                                text: qsTr("Back")
                                color: bridge.configBackOn ? "#ff7a3c" : "#6a7280"
                                font.pixelSize: 12
                                MouseArea {
                                    anchors.fill: parent
                                    enabled: bridge.configBackOn
                                    onClicked: bridge.configBack()
                                }
                            }
                            Text {
                                width: Math.max(40, configBar.width - 280)
                                height: 28
                                verticalAlignment: Text.AlignVCenter
                                text: bridge.configCrumb || qsTr("Drop a config.txt, or open one from the library")
                                color: bridge.dark ? "#d5dbe3" : "#1d1d1f"
                                font.pixelSize: 12
                                elide: Text.ElideRight
                            }
                            Rectangle {
                                width: 160
                                height: 28
                                radius: 8
                                visible: !bridge.configSource
                                color: Qt.rgba(0, 0, 0, bridge.dark ? 0.35 : 0.06)
                                TextInput {
                                    anchors.fill: parent
                                    anchors.leftMargin: 8
                                    anchors.rightMargin: 8
                                    verticalAlignment: TextInput.AlignVCenter
                                    color: bridge.dark ? "#f2f4f8" : "#1d1d1f"
                                    font.pixelSize: 12
                                    clip: true
                                    selectByMouse: true
                                    Text {
                                        anchors.fill: parent
                                        verticalAlignment: Text.AlignVCenter
                                        text: qsTr("Filter tags")
                                        color: "#8b93a1"
                                        font.pixelSize: 12
                                        visible: !parent.text
                                    }
                                    onTextChanged: bridge.setConfigFilter(text)
                                }
                            }
                            Text {
                                width: 52
                                height: 28
                                verticalAlignment: Text.AlignVCenter
                                horizontalAlignment: Text.AlignRight
                                text: bridge.configSource ? qsTr("Tags") : qsTr("Source")
                                color: "#ff7a3c"
                                font.pixelSize: 12
                                MouseArea {
                                    anchors.fill: parent
                                    onClicked: bridge.setConfigSource(!bridge.configSource)
                                }
                            }
                        }
                        TextEdit {
                            visible: bridge.configSource
                            anchors.top: configBar.bottom
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.bottom: parent.bottom
                            anchors.margins: 10
                            color: bridge.dark ? "#f2f4f8" : "#1d1d1f"
                            font.family: "Consolas"
                            font.pixelSize: 13
                            wrapMode: TextEdit.NoWrap
                            selectByMouse: true
                            text: bridge.configText
                            onTextChanged: bridge.configText = text
                        }
                        ListView {
                            id: configList
                            visible: !bridge.configSource
                            anchors.top: configBar.bottom
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.bottom: parent.bottom
                            anchors.margins: 10
                            clip: true
                            spacing: 8
                            model: configPane.configModel
                            delegate: Item {
                                id: configLine
                                required property var modelData
                                width: configList.width
                                property bool proseOpen: false
                                readonly property bool prose: modelData.cells && modelData.cells.length === 1 && modelData.cells[0].lines > 1
                                readonly property int rowHeight: {
                                    if (!modelData.cells)
                                        return 52
                                    var h = 52
                                    for (var i = 0; i < modelData.cells.length; ++i) {
                                        var cell = modelData.cells[i]
                                        if (cell.options && cell.options.length)
                                            h = Math.max(h, 74)
                                    }
                                    return h
                                }
                                onModelDataChanged: proseOpen = false
                                height: modelData.gap ? 28 : (prose ? (proseOpen ? proseFull : 48) : rowHeight)
                                readonly property int proseFull: {
                                    if (!prose)
                                        return 48
                                    return Math.min(320, Math.max(96, 24 + proseMeasure.implicitHeight))
                                }
                                Behavior on height { NumberAnimation { duration: 220; easing.type: Easing.OutCubic } }
                                clip: true
                                Text {
                                    id: proseMeasure
                                    visible: false
                                    width: configList.width - 16
                                    wrapMode: Text.Wrap
                                    font.pixelSize: 12
                                    text: configLine.prose && configLine.modelData.cells[0].value ? configLine.modelData.cells[0].value : ""
                                }
                                Text {
                                    visible: configLine.modelData.gap === true
                                    anchors.left: parent.left
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: configLine.modelData.label || ""
                                    color: bridge.dark ? "#8b93a1" : "#5c6570"
                                    font.pixelSize: 11
                                    font.bold: true
                                    font.capitalization: Font.AllUppercase
                                }
                                Rectangle {
                                    visible: configLine.modelData.gap === true
                                    anchors.left: parent.left
                                    anchors.leftMargin: 88
                                    anchors.right: parent.right
                                    anchors.verticalCenter: parent.verticalCenter
                                    height: 1
                                    color: Qt.rgba(1, 1, 1, bridge.dark ? 0.10 : 0.35)
                                }
                                Row {
                                    anchors.fill: parent
                                    spacing: 10
                                    visible: configLine.modelData.gap !== true
                                    Repeater {
                                        model: configLine.modelData.cells || []
                                        delegate: ConfigField {
                                            required property var modelData
                                            readonly property int span: modelData.span || 1
                                            width: {
                                                var n = configLine.modelData.cells.length
                                                var gaps = Math.max(0, n - 1) * 10
                                                return (configList.width - gaps) * span / 6
                                            }
                                            height: configLine.prose ? configLine.height : configLine.rowHeight
                                            expanded: configLine.proseOpen
                                            onToggled: configLine.proseOpen = !configLine.proseOpen
                                            cell: modelData
                                            onCommit: function(index, text) { bridge.configSet(index, text) }
                                            onPick: function(index) { bridge.configPick(index) }
                                            onBrowse: function(index) { bridge.configBrowse(index) }
                                            onOpen: function(index) { bridge.configOpen(index) }
                                            onMenu: function(cell) { configPane.openMenu(cell) }
                                        }
                                    }
                                }
                            }
                        }
                        Rectangle {
                            visible: configPane.menuCell !== null
                            anchors.fill: parent
                            color: Qt.rgba(0, 0, 0, 0.35)
                            z: 20
                            MouseArea { anchors.fill: parent; onClicked: configPane.menuCell = null }
                        }
                        Rectangle {
                            id: menuCard
                            visible: configPane.menuCell !== null
                            z: 21
                            width: Math.min(520, parent.width - 48)
                            height: Math.min(520, parent.height - 48)
                            anchors.centerIn: parent
                            radius: 14
                            clip: true
                            color: bridge.dark ? "#1a2230" : "#f7f8fa"
                            border.width: 1
                            border.color: Qt.rgba(1, 1, 1, bridge.dark ? 0.14 : 0.5)
                            onVisibleChanged: if (visible) menuSearch.forceActiveFocus()
                            Column {
                                anchors.fill: parent
                                anchors.margins: 14
                                spacing: 8
                                Text {
                                    width: parent.width
                                    text: configPane.menuCell ? configPane.menuCell.name : ""
                                    color: bridge.dark ? "#f2f4f8" : "#1d1d1f"
                                    font.pixelSize: 15
                                    font.bold: true
                                    elide: Text.ElideRight
                                }
                                Text {
                                    width: parent.width
                                    visible: configPane.menuCell && configPane.menuCell.name === "trainz-build"
                                    text: qsTr("Writes the trainz-build number. Several game builds share one number.")
                                    color: "#8b93a1"
                                    font.pixelSize: 11
                                    wrapMode: Text.WordWrap
                                }
                                Rectangle {
                                    width: parent.width
                                    height: 34
                                    radius: 8
                                    color: Qt.rgba(0, 0, 0, bridge.dark ? 0.38 : 0.06)
                                    border.width: 1
                                    border.color: Qt.rgba(1, 1, 1, bridge.dark ? 0.08 : 0.3)
                                    TextInput {
                                        id: menuSearch
                                        anchors.fill: parent
                                        anchors.leftMargin: 10
                                        anchors.rightMargin: 10
                                        verticalAlignment: TextInput.AlignVCenter
                                        color: bridge.dark ? "#f2f4f8" : "#1d1d1f"
                                        font.pixelSize: 13
                                        selectByMouse: true
                                        text: configPane.menuQuery
                                        onTextChanged: configPane.menuQuery = text
                                    }
                                    Text {
                                        anchors.left: parent.left
                                        anchors.leftMargin: 10
                                        anchors.verticalCenter: parent.verticalCenter
                                        text: qsTr("Search code or name")
                                        color: "#8b93a1"
                                        font.pixelSize: 13
                                        visible: configPane.menuQuery.length === 0
                                    }
                                }
                                Row {
                                    width: parent.width
                                    height: 16
                                    spacing: 8
                                    Text {
                                        width: 72
                                        text: configPane.menuCell && configPane.menuCell.name === "trainz-build" ? qsTr("Build") : qsTr("Code")
                                        color: "#8b93a1"
                                        font.pixelSize: 10
                                        font.bold: true
                                    }
                                    Text {
                                        text: configPane.menuCell && configPane.menuCell.name === "trainz-build" ? qsTr("Game") : qsTr("Name")
                                        color: "#8b93a1"
                                        font.pixelSize: 10
                                        font.bold: true
                                    }
                                }
                                ListView {
                                    id: menuList
                                    width: parent.width
                                    height: parent.height - (configPane.menuCell && configPane.menuCell.name === "trainz-build" ? 148 : 128)
                                    clip: true
                                    boundsBehavior: Flickable.StopAtBounds
                                    model: configPane.menuHits()
                                    delegate: Rectangle {
                                        required property var modelData
                                        required property int index
                                        width: menuList.width
                                        height: 34
                                        radius: 6
                                        property bool hot: false
                                        color: {
                                            if (configPane.menuHas(modelData.code))
                                                return Qt.rgba(1, 0.42, 0.14, bridge.dark ? 0.38 : 0.28)
                                            if (hot)
                                                return Qt.rgba(1, 1, 1, bridge.dark ? 0.08 : 0.16)
                                            return index % 2 ? Qt.rgba(1, 1, 1, bridge.dark ? 0.05 : 0.72) : Qt.rgba(0, 0, 0, bridge.dark ? 0.28 : 0.05)
                                        }
                                        Row {
                                            anchors.fill: parent
                                            anchors.leftMargin: 8
                                            anchors.rightMargin: 8
                                            spacing: 8
                                            Text {
                                                width: 72
                                                height: parent.height
                                                verticalAlignment: Text.AlignVCenter
                                                text: modelData.code === modelData.label ? "" : modelData.code
                                                color: "#ff7a3c"
                                                font.family: "Consolas"
                                                font.pixelSize: 12
                                                elide: Text.ElideRight
                                            }
                                            Text {
                                                width: parent.width - 80
                                                height: parent.height
                                                verticalAlignment: Text.AlignVCenter
                                                text: modelData.label
                                                color: bridge.dark ? "#f2f4f8" : "#1d1d1f"
                                                font.pixelSize: 13
                                                elide: Text.ElideRight
                                            }
                                        }
                                        MouseArea {
                                            anchors.fill: parent
                                            hoverEnabled: true
                                            onEntered: parent.hot = true
                                            onExited: parent.hot = false
                                            onClicked: configPane.menuPick(modelData.code)
                                        }
                                    }
                                }
                                Rectangle {
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    width: 88
                                    height: 28
                                    radius: 8
                                    color: "#ff7a3c"
                                    Text {
                                        anchors.centerIn: parent
                                        text: configPane.menuCell && configPane.menuCell.multi ? qsTr("Done") : qsTr("Close")
                                        color: "#ffffff"
                                        font.pixelSize: 12
                                        font.bold: true
                                    }
                                    MouseArea {
                                        anchors.fill: parent
                                        onClicked: configPane.menuCell = null
                                    }
                                }
                            }
                        }
                    }
                    TextEdit {
                        visible: bridge.page === "kuid"
                        width: parent.width
                        height: parent.height * 0.42
                        color: bridge.dark ? "#f2f4f8" : "#1d1d1f"
                        font.family: "Consolas"
                        font.pixelSize: 13
                        wrapMode: TextEdit.NoWrap
                        selectByMouse: true
                        text: bridge.kuidIn
                        onTextChanged: bridge.kuidIn = text
                    }
                    TextEdit {
                        visible: bridge.page === "export"
                        width: parent.width
                        height: 120
                        color: bridge.dark ? "#f2f4f8" : "#1d1d1f"
                        font.family: "Consolas"
                        font.pixelSize: 13
                        wrapMode: TextEdit.NoWrap
                        selectByMouse: true
                        text: bridge.exportIn
                        onTextChanged: bridge.exportIn = text
                    }
                    Text {
                        visible: bridge.page === "kuid"
                        width: parent.width
                        color: bridge.dark ? "#8b93a1" : "#5c6570"
                        font.pixelSize: 12
                        text: (typeof bridge.kuidOut === "string" ? qsTr(bridge.kuidOut) : bridge.kuidOut)
                        wrapMode: Text.Wrap
                    }
                    ListView {
                        id: exportList
                        visible: bridge.page === "export"
                        width: parent.width
                        height: Math.max(40, parent.height - 140)
                        clip: true
                        spacing: 4
                        model: {
                            try { return JSON.parse(bridge.exportJson) }
                            catch (e) { return [] }
                        }
                        delegate: Rectangle {
                            required property var modelData
                            width: exportList.width
                            height: 36
                            radius: 8
                            color: Qt.rgba(1, 1, 1, bridge.dark ? 0.05 : 0.45)
                            Text {
                                anchors.left: parent.left
                                anchors.leftMargin: 10
                                anchors.verticalCenter: parent.verticalCenter
                                width: parent.width * 0.62
                                text: (typeof modelData.kuid === "string" ? qsTr(modelData.kuid) : modelData.kuid)
                                color: bridge.dark ? "#f2f4f8" : "#1d1d1f"
                                font.pixelSize: 12
                                elide: Text.ElideRight
                            }
                            Text {
                                anchors.right: parent.right
                                anchors.rightMargin: 10
                                anchors.verticalCenter: parent.verticalCenter
                                text: (typeof modelData.status === "string" ? qsTr(modelData.status) : modelData.status)
                                color: bridge.dark ? "#8b93a1" : "#5c6570"
                                font.pixelSize: 11
                            }
                        }
                    }
                }

                function sync() {
                    if (stage.layoutDrag)
                        return
                    if (!visible || width < 8 || height < 8) {
                        bridge.placeCenter(0, 0, 0, 0)
                        return
                    }
                    var p = mapToItem(root, 0, 0)
                    bridge.placeCenter(p.x, p.y, width, height)
                }
                onXChanged: sync()
                onYChanged: sync()
                onWidthChanged: sync()
                onHeightChanged: sync()
            }
        }

        MouseArea {
            z: 3
            x: side.width - 3
            y: 0
            width: 10
            height: parent.height
            cursorShape: Qt.SplitHCursor
            property real pressX: 0
            property real grabW: 0
            onPressed: {
                pressX = mapToItem(stage, mouseX, 0).x
                grabW = stage.sideLive
                stage.beginDrag()
            }
            onPositionChanged: {
                if (!pressed)
                    return
                var now = mapToItem(stage, mouseX, 0).x
                stage.sideLive = Math.max(320, Math.min(560, Math.round(grabW + (now - pressX))))
            }
            onReleased: stage.endDrag()
            onCanceled: stage.endDrag()
        }

        MouseArea {
            z: 30
            enabled: bridge.dockOn && dockSlot.width > 40
            x: dockSlot.x - 10
            y: 0
            width: 16
            height: parent.height
            cursorShape: Qt.SplitHCursor
            preventStealing: true
            property real pressX: 0
            property real grabW: 0
            onPressed: {
                pressX = mapToItem(stage, mouseX, 0).x
                grabW = stage.dockLive
                stage.beginDrag()
            }
            onPositionChanged: {
                if (!pressed)
                    return
                var now = mapToItem(stage, mouseX, 0).x
                var cap = stage.dockCap()
                var next = Math.max(280, Math.min(cap, Math.round(grabW - (now - pressX))))
                stage.dockLive = next
                stage.dockUser = next < cap - 2
            }
            onReleased: stage.endDrag()
            onCanceled: stage.endDrag()
        }
    }

    FontLoader {
        id: mi
        source: bridge.iconFontUrl
    }

    Item {
        id: nav
        // Full bar, centered in the gap between the sidebars.
        // When the right dock opens and the gap is narrower than the bar, slide left so the bar stays clear of that dock.
        readonly property real laneLeft: stage.x + side.width + 8
        readonly property real laneRight: dockSlot.width > 8 ? (stage.x + dockSlot.x - 8) : (stage.x + stage.width - 8)
        anchors.bottom: parent.bottom
        anchors.bottomMargin: chrome.barMargin
        width: Math.min(root.width - 32, Math.max(420, cluster.width + 40))
        x: {
            var lane = laneRight - laneLeft
            var mid = laneLeft + (lane - width) / 2
            if (width > lane)
                mid = laneRight - width
            return Math.max(8, Math.min(mid, root.width - width - 8))
        }
        height: bridge.navTall ? 100 : 76
        z: 20
        // Dock width already eases. A second ease on x restarts every frame and stutters.

        GlassPlate {
            anchors.fill: parent
            dark: bridge.dark
            quiet: stage.layoutDrag || dockEase.running
            plateRadius: 28
            foot: 10
        }

        Item {
            id: cluster
            anchors.centerIn: parent
            width: leftWell.width + homeGap + homeWell.width + homeGap + rightWell.width
            height: bridge.navTall ? 68 : 48
            property int homeGap: bridge.navTall ? 18 : 14

            function findChip(page) {
                var i
                for (i = 0; i < leftRep.count; i++) {
                    var a = leftRep.itemAt(i)
                    if (a && a.pageKey === page)
                        return a
                }
                for (i = 0; i < rightRep.count; i++) {
                    var b = rightRep.itemAt(i)
                    if (b && b.pageKey === page)
                        return b
                }
                return null
            }

            function firstKey() {
                var chip = leftRep.count > 0 ? leftRep.itemAt(0) : null
                return chip ? chip.pageKey : ""
            }

            function chipRow(chip) {
                var i
                for (i = 0; i < leftRep.count; i++) {
                    if (leftRep.itemAt(i) === chip)
                        return leftRow
                }
                return rightRow
            }

            function placePill(page, animate) {
                var chip = findChip(page)
                if (!chip || chip.width < 8) {
                    if (pillTries < 15)
                        pillRetry.restart()
                    return
                }
                var row = chipRow(chip)
                if (row.width < 40) {
                    if (pillTries < 15)
                        pillRetry.restart()
                    return
                }
                var at = chip.mapToItem(cluster, 0, 0)
                var rowAt = row.mapToItem(cluster, 0, 0)
                // Row still at the pre-layout origin; accepting that parks the pill off the label.
                if (Math.abs(at.y - rowAt.y) > 1 || rowAt.y < 1) {
                    if (pillTries < 15)
                        pillRetry.restart()
                    return
                }
                // A later chip stays at x 0 until the Row places it. That lands the pill on Mesh Lods.
                var firstInRow = row === leftRow
                        ? (leftRep.count > 0 && leftRep.itemAt(0) === chip)
                        : (rightRep.count > 0 && rightRep.itemAt(0) === chip)
                if (!firstInRow && chip.x < 8) {
                    if (pillTries < 15)
                        pillRetry.restart()
                    return
                }
                pillTries = 0
                pill.visible = true
                if (!animate) {
                    if (pillSliding)
                        return
                    pill.x = at.x
                    pill.y = at.y + 4
                    pill.width = chip.width
                    pill.height = Math.max(28, chip.height - 8)
                    return
                }
                pillSliding = true
                slideX.to = at.x
                slideY.to = at.y + 4
                slideW.to = chip.width
                slideH.to = Math.max(28, chip.height - 8)
                slideX.start()
                slideY.start()
                slideW.start()
                slideH.start()
            }

            property int pillTries: 0
            property bool pillSliding: false
            Timer {
                id: pillRetry
                interval: 40
                repeat: false
                onTriggered: {
                    cluster.pillTries += 1
                    cluster.placePill(bridge.page, false)
                }
            }

            Rectangle {
                id: leftWell
                z: 0
                y: 2
                width: Math.max(80, leftRow.width + 12)
                height: parent.height - 4
                radius: 16
                color: Qt.rgba(0, 0, 0, bridge.dark ? 0.32 : 0.06)
                border.width: 1
                border.color: Qt.rgba(1, 1, 1, bridge.dark ? 0.08 : 0.40)
            }

            Rectangle {
                id: homeWell
                z: 3
                x: leftWell.width + cluster.homeGap
                y: 2
                width: bridge.navTall ? 52 : 48
                height: parent.height - 4
                radius: 16
                color: homeH.hovered ? Qt.rgba(1, 0.35, 0.16, 0.35) : Qt.rgba(0, 0, 0, bridge.dark ? 0.22 : 0.05)
                border.width: 1
                border.color: Qt.rgba(1, 1, 1, bridge.dark ? 0.16 : 0.55)

                Text {
                    z: 2
                    anchors.centerIn: parent
                    text: (typeof bridge.homeLabel === "string" ? qsTr(bridge.homeLabel) : bridge.homeLabel)
                    font.family: mi.name.length > 0 ? mi.name : bridge.iconFont
                    font.pixelSize: bridge.navTall ? 24 : 22
                    color: homeH.hovered ? "#ff5a1f" : (bridge.dark ? "#f4f6fa" : "#1c1c1e")
                }
                HoverHandler { id: homeH }
                TapHandler { onTapped: bridge.goHome() }
            }

            Rectangle {
                id: rightWell
                z: 0
                x: homeWell.x + homeWell.width + cluster.homeGap
                y: 2
                width: Math.max(80, rightRow.width + 12)
                height: parent.height - 4
                radius: 16
                color: Qt.rgba(0, 0, 0, bridge.dark ? 0.32 : 0.06)
                border.width: 1
                border.color: Qt.rgba(1, 1, 1, bridge.dark ? 0.08 : 0.40)
            }

            Rectangle {
                id: pill
                z: 1
                visible: false
                y: 6
                x: 6
                width: 100
                height: 36
                radius: 12
                color: "#ff5a1f"
                Rectangle {
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.leftMargin: 14
                    anchors.rightMargin: 14
                    anchors.topMargin: 1
                    height: 1
                    color: Qt.rgba(1, 1, 1, 0.55)
                }
                transform: Scale {
                    id: pillScale
                    origin.x: pill.width / 2
                    origin.y: pill.height / 2
                }
            }
            NumberAnimation {
                id: slideX
                target: pill
                property: "x"
                duration: 280
                easing.type: Easing.OutCubic
                onFinished: {
                    cluster.pillSliding = false
                    cluster.placePill(bridge.page, false)
                    pillPop.restart()
                }
            }
            NumberAnimation { id: slideY; target: pill; property: "y"; duration: 280; easing.type: Easing.OutCubic }
            NumberAnimation { id: slideW; target: pill; property: "width"; duration: 280; easing.type: Easing.OutCubic }
            NumberAnimation { id: slideH; target: pill; property: "height"; duration: 280; easing.type: Easing.OutCubic }
            SequentialAnimation {
                id: pillPop
                NumberAnimation { target: pillScale; properties: "xScale,yScale"; to: 1.06; duration: 120; easing.type: Easing.OutCubic }
                NumberAnimation { target: pillScale; properties: "xScale,yScale"; to: 1.0; duration: 200; easing.type: Easing.OutBack }
            }

            component NavChip: Item {
                property string pageKey: ""
                property string label: ""
                property int chipW: 96
                readonly property bool hot: bridge.page === pageKey
                width: chipW
                height: label.indexOf("\n") >= 0 ? 60 : 44
                z: 2
                Text {
                    z: 2
                    anchors.horizontalCenter: parent.horizontalCenter
                    anchors.verticalCenter: parent.verticalCenter
                    width: parent.width - 4
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.WordWrap
                    text: (typeof label === "string" ? qsTr(label) : label)
                    color: hot ? "#ffffff" : (bridge.dark ? "#f4f6fa" : "#1c1c1e")
                    font.pixelSize: 12
                    font.bold: hot
                }
                HoverHandler { id: chipH }
                Rectangle {
                    anchors.fill: parent
                    anchors.margins: 4
                    radius: 10
                    z: -1
                    color: (!hot && chipH.hovered) ? Qt.rgba(1, 1, 1, bridge.dark ? 0.10 : 0.45) : "transparent"
                }
                TapHandler { onTapped: bridge.setPage(pageKey) }
            }

            // Declared after the pill. Its Scale layer would otherwise cover these labels.
            Row {
                id: leftRow
                z: 3
                x: leftWell.x + (leftWell.width - width) / 2
                y: leftWell.y + (leftWell.height - height) / 2
                spacing: 0
                onXChanged: if (!cluster.pillSliding) Qt.callLater(function() { cluster.placePill(bridge.page, false) })
                onYChanged: if (!cluster.pillSliding) Qt.callLater(function() { cluster.placePill(bridge.page, false) })
                onWidthChanged: if (!cluster.pillSliding) Qt.callLater(function() { cluster.placePill(bridge.page, false) })
                Repeater {
                    id: leftRep
                    model: cluster.leftModel
                    delegate: NavChip {
                        required property var modelData
                        pageKey: modelData.key
                        label: (typeof modelData.label === "string" ? qsTr(modelData.label) : modelData.label)
                        chipW: modelData.w
                    }
                }
            }

            Row {
                id: rightRow
                z: 3
                x: rightWell.x + (rightWell.width - width) / 2
                y: rightWell.y + (rightWell.height - height) / 2
                spacing: 0
                onXChanged: if (!cluster.pillSliding) Qt.callLater(function() { cluster.placePill(bridge.page, false) })
                onYChanged: if (!cluster.pillSliding) Qt.callLater(function() { cluster.placePill(bridge.page, false) })
                onWidthChanged: if (!cluster.pillSliding) Qt.callLater(function() { cluster.placePill(bridge.page, false) })
                Repeater {
                    id: rightRep
                    model: cluster.rightModel
                    delegate: NavChip {
                        required property var modelData
                        pageKey: modelData.key
                        label: (typeof modelData.label === "string" ? qsTr(modelData.label) : modelData.label)
                        chipW: modelData.w
                    }
                }
            }

            property string tracked: bridge.page + "|" + bridge.suite
            property string leftRaw: bridge.leftNavJson
            property string rightRaw: bridge.rightNavJson
            property var leftModel: []
            property var rightModel: []
            onLeftRawChanged: {
                try { leftModel = JSON.parse(leftRaw) }
                catch (e) { leftModel = [] }
            }
            onRightRawChanged: {
                try { rightModel = JSON.parse(rightRaw) }
                catch (e) { rightModel = [] }
            }
            property bool slideArmed: false
            onTrackedChanged: if (slideArmed) {
                pillTries = 0
                Qt.callLater(function() { placePill(bridge.page, true) })
            }
            Component.onCompleted: Qt.callLater(function() {
                cluster.onLeftRawChanged()
                cluster.onRightRawChanged()
                placePill(bridge.page, false)
                slideArmed = true
            })
        }
    }

    Connections {
        target: bridge
        function onChanged() {
            queueSlot.sync()
            dockSlot.sync()
            previewSlot.sync()
            formToolSlot.sync()
            centerBody.sync()
            centerChrome.syncWells()
        }
    }
}
