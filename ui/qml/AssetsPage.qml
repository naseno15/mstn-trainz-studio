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
            GradientStop { position: 1.0; color: bridge.dark ? "#0c0e12" : "#d5dbe3" }
        }
    }

    Item {
        id: stage
        property bool dockDrag: false
        anchors.fill: parent
        anchors.leftMargin: 10
        anchors.rightMargin: 10
        anchors.topMargin: 8
        anchors.bottomMargin: chrome.stageMargin

        AssetsSide {
            id: side
            anchors.left: parent.left
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            width: bridge.sideW
            footPad: {
                var o = mapToItem(root, 0, 0)
                if (o.x + width <= nav.x + 8 || o.x >= nav.x + nav.width - 8)
                    return 0
                return chrome.contentInset(nav.height)
            }
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
            width: bridge.dockOn ? (bridge.viewerExpanded ? parent.width - side.width - 8 : bridge.dockW) : 0
            property bool widthReady: false
            Behavior on width {
                enabled: dockSlot.widthReady && !stage.dockDrag
                NumberAnimation { duration: 280; easing.type: Easing.OutCubic }
            }

            AssetsViewer {
                id: viewerChrome
                anchors.fill: parent
                visible: bridge.viewerOn && dockSlot.width > 40
            }

            AssetsDock {
                id: formChrome
                anchors.fill: parent
                visible: bridge.formOn && dockSlot.width > 40
            }

            GlassPlate {
                anchors.fill: parent
                visible: !bridge.viewerOn && !bridge.formOn && dockSlot.width > 40
                dark: bridge.dark
                plateRadius: 16
                foot: 8
            }

            Item {
                id: previewSlot
                anchors.fill: parent
                anchors.leftMargin: 16
                anchors.rightMargin: 16
                anchors.topMargin: viewerChrome.padTop
                anchors.bottomMargin: viewerChrome.padBottom
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
                    visible: bridge.viewPane === 0 && bridge.previewImage.length === 0 && !bridge.previewAudio
                    anchors.fill: parent
                    anchors.margins: 10
                    contentWidth: viewerText.implicitWidth
                    contentHeight: viewerText.implicitHeight
                    clip: true
                    TextEdit {
                        id: viewerText
                        width: Math.max(previewSlot.width, implicitWidth)
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
                    visible: bridge.viewPane === 1
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
                        width: Math.max(previewSlot.width, implicitWidth)
                        readOnly: false
                        selectByMouse: true
                        wrapMode: TextEdit.NoWrap
                        textFormat: TextEdit.PlainText
                        color: bridge.dark ? "#f2f4f8" : "#1d1d1f"
                        selectionColor: "#ff5a1f"
                        font.family: "Consolas"
                        font.pixelSize: bridge.previewPt + 2
                        text: bridge.previewPlain
                        onTextChanged: if (bridge.viewPane === 1) bridge.setPreviewText(text)
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
                    visible: bridge.viewPane === 1
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
                    Column {
                        x: 0
                        y: 10 - editorFlick.contentY
                        width: parent.width - 7
                        Repeater {
                            model: Math.max(1, editorText.lineCount)
                            Text {
                                required property int index
                                width: parent.width
                                height: editorMetrics.lineSpacing
                                horizontalAlignment: Text.AlignRight
                                verticalAlignment: Text.AlignVCenter
                                text: index + 1
                                color: "#858585"
                                font.family: "Consolas"
                                font.pixelSize: bridge.previewPt
                            }
                        }
                    }
                }

                function sync() {
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
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                anchors.top: parent.top
                anchors.leftMargin: 16
                anchors.rightMargin: 16
                anchors.bottomMargin: 16
                anchors.topMargin: formChrome.padTop
                visible: bridge.formTool && dockSlot.width > 40

                function sync() {
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

            AssetsCenter {
                id: centerChrome
                anchors.fill: parent
            }

            Item {
                id: centerBody
                visible: bridge.centerKind === "page"
                anchors.fill: parent
                anchors.leftMargin: centerChrome.padSide
                anchors.rightMargin: centerChrome.padSide
                anchors.topMargin: centerChrome.padTop
                anchors.bottomMargin: centerChrome.padBottom

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
                                                text: (typeof modelData.title === "string" ? qsTr(modelData.title) : modelData.title)
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
                                spacing: 2
                                boundsBehavior: Flickable.StopAtBounds
                                model: centerBody.finderRows
                                delegate: Item {
                                    required property var modelData
                                    width: finderList.width
                                    height: 52
                                    HoverHandler { id: rowHover }

                                    Item {
                                        anchors.fill: parent
                                        anchors.leftMargin: 6
                                        anchors.rightMargin: 6
                                        anchors.topMargin: 3
                                        anchors.bottomMargin: 3
                                        visible: modelData.on

                                        Repeater {
                                            model: 3
                                            delegate: Rectangle {
                                                required property int index
                                                property real t: (index + 1) / 3
                                                anchors.fill: parent
                                                anchors.leftMargin: 1 - t * 2
                                                anchors.rightMargin: 1 - t * 2
                                                anchors.topMargin: 1 + index
                                                anchors.bottomMargin: -t * 2
                                                radius: 12
                                                color: Qt.rgba(0, 0, 0, 0.28 * (1.05 - t))
                                            }
                                        }
                                        Rectangle {
                                            anchors.fill: parent
                                            anchors.bottomMargin: 2
                                            radius: 12
                                            gradient: Gradient {
                                                GradientStop { position: 0.0; color: "#ff7a45" }
                                                GradientStop { position: 0.42; color: "#ff5a1f" }
                                                GradientStop { position: 1.0; color: "#c43a10" }
                                            }
                                            border.width: 1
                                            border.color: Qt.rgba(1, 0.84, 0.70, 0.60)
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
                                        }
                                    }
                                    Rectangle {
                                        anchors.fill: parent
                                        anchors.leftMargin: 6
                                        anchors.rightMargin: 6
                                        anchors.topMargin: 3
                                        anchors.bottomMargin: 3
                                        radius: 12
                                        visible: !modelData.on && rowHover.hovered
                                        color: Qt.rgba(1, 1, 1, bridge.dark ? 0.08 : 0.35)
                                        border.width: 1
                                        border.color: Qt.rgba(1, 1, 1, bridge.dark ? 0.10 : 0.40)
                                    }
                                    Row {
                                        z: 2
                                        anchors.fill: parent
                                        Item {
                                            width: finderHeader.nameWidth
                                            height: parent.height
                                            Rectangle {
                                                x: 14
                                                width: 28
                                                height: 28
                                                radius: 8
                                                anchors.verticalCenter: parent.verticalCenter
                                                property color badgeColor: modelData.color || "#8e8e93"
                                                color: modelData.on ? Qt.rgba(0, 0, 0, 0.22) : Qt.rgba(badgeColor.r, badgeColor.g, badgeColor.b, 0.22)
                                                Text {
                                                    anchors.centerIn: parent
                                                    text: modelData.badge || qsTr("\u00b7")
                                                    color: modelData.on ? "#ffffff" : modelData.color
                                                    font.pixelSize: 12
                                                    font.bold: true
                                                }
                                            }
                                            Text {
                                                x: 52
                                                width: parent.width - 62
                                                anchors.verticalCenter: parent.verticalCenter
                                                text: (typeof modelData.name === "string" ? qsTr(modelData.name) : modelData.name)
                                                color: modelData.on ? "#ffffff" : (bridge.dark ? "#f2f4f8" : "#1d1d1f")
                                                font.pixelSize: 12
                                                font.bold: true
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
                                        onDoubleTapped: if (modelData.kind === "asset" || modelData.kind === "dir") bridge.openFinder(modelData.row)
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
                        visible: bridge.page === "config"
                        width: parent.width
                        height: parent.height - 8
                        Rectangle {
                            anchors.fill: parent
                            radius: 12
                            color: Qt.rgba(0, 0, 0, bridge.dark ? 0.38 : 0.08)
                            border.width: 1
                            border.color: Qt.rgba(1, 1, 1, bridge.dark ? 0.12 : 0.40)
                        }
                        TextEdit {
                            anchors.fill: parent
                            anchors.margins: 10
                            color: bridge.dark ? "#f2f4f8" : "#1d1d1f"
                            font.family: "Consolas"
                            font.pixelSize: 13
                            wrapMode: TextEdit.NoWrap
                            selectByMouse: true
                            text: bridge.configText
                            onTextChanged: bridge.configText = text
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
            property real lastX: 0
            onPressed: lastX = mapToItem(stage, mouseX, 0).x
            onPositionChanged: {
                if (!pressed)
                    return
                var now = mapToItem(stage, mouseX, 0).x
                bridge.setSideW(side.width + (now - lastX))
                lastX = now
            }
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
            property real lastX: 0
            property real grabW: 0
            onPressed: {
                stage.dockDrag = true
                lastX = mapToItem(stage, mouseX, 0).x
                grabW = bridge.dockW
            }
            onPositionChanged: {
                if (!pressed)
                    return
                var now = mapToItem(stage, mouseX, 0).x
                bridge.setDockW(grabW - (now - lastX))
            }
            onReleased: stage.dockDrag = false
            onCanceled: stage.dockDrag = false
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
