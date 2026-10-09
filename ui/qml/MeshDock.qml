import QtQuick

// Right Editor dock. Fields write back into the hidden editor widgets.
Item {
    id: dock

    readonly property var bag: {
        try { return JSON.parse(bridge.dockJson) } catch (e) { return {} }
    }
    readonly property var mat: bag.mat || {}
    readonly property var att: bag.att || {}
    readonly property color ink: bridge.dark ? "#f4f6fa" : "#1c1c1e"
    readonly property color mute: bridge.dark ? "#9aa3b2" : "#5c6570"

    FontLoader { id: mi; source: bridge.iconFontUrl }

    Column {
        id: head
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        spacing: 4
        Text { text: dock.bag.title || ""; color: dock.ink; font.pixelSize: 14; font.bold: true }
        Text { text: dock.bag.sub || ""; color: dock.mute; font.pixelSize: 11; width: parent.width; wrapMode: Text.Wrap }
        Text {
            visible: (dock.bag.tip || "").length > 0
            text: dock.bag.tip || ""
            color: dock.mute
            font.pixelSize: 11
            width: parent.width
            wrapMode: Text.Wrap
        }
    }

    Flickable {
        anchors.top: head.bottom
        anchors.topMargin: 8
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: foot.top
        anchors.bottomMargin: 8
        contentWidth: width
        contentHeight: form.implicitHeight
        clip: true

        Column {
            id: form
            width: parent.width
            spacing: 6

            Column {
                width: parent.width
                spacing: 6
                visible: dock.bag.mode === "meshes"
                Field { label: "Name"; live: dock.mat.name || ""; onCommit: function (t) { bridge.setText("matName", t) } }
                Text { text: "Type"; color: dock.mute; font.pixelSize: 11 }
                Flow {
                    width: parent.width
                    spacing: 4
                    Repeater {
                        model: dock.mat.types || []
                        delegate: Rectangle {
                            required property string modelData
                            required property int index
                            width: tl.implicitWidth + 12
                            height: 26
                            radius: 8
                            color: index === dock.mat.type ? "#ff5a1f" : "transparent"
                            Text { id: tl; anchors.centerIn: parent; text: modelData; color: index === dock.mat.type ? "#fff" : dock.ink; font.pixelSize: 11 }
                            TapHandler { onTapped: bridge.setCombo("type", index) }
                        }
                    }
                }
                Text {
                    text: dock.mat.two ? "☑ Double Sided" : "☐ Double Sided"
                    color: dock.ink
                    font.pixelSize: 12
                    TapHandler { onTapped: bridge.setChecked("two", !dock.mat.two) }
                }
                Text { text: "Vertices  " + (dock.mat.vfmt || "—"); color: dock.mute; font.pixelSize: 12 }
                Text { text: "Textures"; color: dock.ink; font.pixelSize: 13; font.bold: true }
                Repeater {
                    model: dock.mat.tex || []
                    delegate: Row {
                        required property var modelData
                        width: form.width
                        height: 32
                        spacing: 6
                        Text { text: modelData.k; color: dock.mute; font.pixelSize: 11; width: 110; elide: Text.ElideRight; anchors.verticalCenter: parent.verticalCenter }
                        Field {
                            width: parent.width - 150
                            live: modelData.v || ""
                            onCommit: function (t) { bridge.setText("tex:" + modelData.k, t) }
                        }
                        Text {
                            text: modelData.lock ? "🔒" : "📁"
                            anchors.verticalCenter: parent.verticalCenter
                            TapHandler { onTapped: if (!modelData.lock) bridge.clickId("texBrowse:" + modelData.k) }
                        }
                    }
                }
                Text { text: "Color"; color: dock.ink; font.pixelSize: 13; font.bold: true }
                Rgba { which: "color"; title: "Material"; ch: dock.mat.color || [0, 0, 0, 255]; pick: "color" }
                Rgba { which: "emis"; title: "Emissive"; ch: dock.mat.emis || [0, 0, 0, 255]; pick: "emisPick" }
                Rgba { which: "spec"; title: "Specular"; ch: dock.mat.specC || [0, 0, 0, 255]; pick: "specPick" }
                Field { label: "specPower"; live: String(dock.mat.spec || 0); onCommit: function (t) { bridge.setSpin("spec", Number(t)) } }
            }

            Column {
                width: parent.width
                spacing: 6
                visible: dock.bag.mode === "attachs"
                Field { label: "Name"; live: dock.att.name || ""; onCommit: function (t) { bridge.setText("attName", t) } }
                Field { label: "Parent"; live: dock.att.parent || ""; onCommit: function (t) { bridge.setText("attParent", t) } }
                Text { text: "Location"; color: dock.ink; font.pixelSize: 13; font.bold: true }
                Field { label: "X"; live: String((dock.att.loc || [0, 0, 0])[0]); onCommit: function (t) { bridge.setSpin("loc0", Number(t)) } }
                Field { label: "Y"; live: String((dock.att.loc || [0, 0, 0])[1]); onCommit: function (t) { bridge.setSpin("loc1", Number(t)) } }
                Field { label: "Z"; live: String((dock.att.loc || [0, 0, 0])[2]); onCommit: function (t) { bridge.setSpin("loc2", Number(t)) } }
                Text { text: "Rotation"; color: dock.ink; font.pixelSize: 13; font.bold: true }
                Field { label: "X"; live: String((dock.att.rot || [0, 0, 0, 1])[0]); onCommit: function (t) { bridge.setSpin("rot0", Number(t)) } }
                Field { label: "Y"; live: String((dock.att.rot || [0, 0, 0, 1])[1]); onCommit: function (t) { bridge.setSpin("rot1", Number(t)) } }
                Field { label: "Z"; live: String((dock.att.rot || [0, 0, 0, 1])[2]); onCommit: function (t) { bridge.setSpin("rot2", Number(t)) } }
                Field { label: "W"; live: String((dock.att.rot || [0, 0, 0, 1])[3]); onCommit: function (t) { bridge.setSpin("rot3", Number(t)) } }
                Row {
                    spacing: 8
                    Text { text: "Apply"; color: dock.bag.applyOn ? "#ff5a1f" : dock.mute; font.pixelSize: 13; font.bold: true; TapHandler { onTapped: if (dock.bag.applyOn) bridge.clickId("apply") } }
                    Text { text: "Add"; color: dock.bag.addOn ? dock.ink : dock.mute; font.pixelSize: 13; TapHandler { onTapped: if (dock.bag.addOn) bridge.clickId("add") } }
                    Text { text: "Delete"; color: dock.bag.delOn ? dock.ink : dock.mute; font.pixelSize: 13; TapHandler { onTapped: if (dock.bag.delOn) bridge.clickId("del") } }
                }
            }
        }
    }

    Row {
        id: foot
        anchors.bottom: parent.bottom
        anchors.left: parent.left
        spacing: 8
        RaiseButton {
            width: 36
            height: 36
            accent: true
            enabled: dock.bag.saveOn === true
            glyph: bridge.saveGlyph
            fontName: mi.name.length > 0 ? mi.name : bridge.iconFont
            tip: "Save"
            onClicked: bridge.clickId("save")
        }
        RaiseButton {
            width: 36
            height: 36
            enabled: dock.bag.saveOn === true
            glyph: bridge.saveGlyph
            fontName: mi.name.length > 0 ? mi.name : bridge.iconFont
            tip: "Save As"
            onClicked: bridge.clickId("saveAs")
        }
    }

    component Field: Item {
        property string label: ""
        property string live: ""
        signal commit(string text)
        width: parent ? parent.width : 200
        height: 32
        Text {
            visible: label.length > 0
            text: label
            color: dock.mute
            font.pixelSize: 11
            width: label.length > 0 ? 72 : 0
            anchors.verticalCenter: parent.verticalCenter
            elide: Text.ElideRight
        }
        Rectangle {
            anchors.left: parent.left
            anchors.leftMargin: label.length > 0 ? 76 : 0
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            height: 28
            radius: 8
            color: Qt.rgba(0, 0, 0, bridge.dark ? 0.28 : 0.06)
            TextInput {
                id: input
                anchors.fill: parent
                anchors.leftMargin: 8
                anchors.rightMargin: 8
                verticalAlignment: TextInput.AlignVCenter
                color: dock.ink
                font.pixelSize: 12
                selectByMouse: true
                clip: true
                text: input.activeFocus ? input.text : live
                onEditingFinished: commit(text)
            }
        }
    }

    component Rgba: Column {
        property string which: ""
        property string title: ""
        property var ch: [0, 0, 0, 255]
        property string pick: ""
        width: parent.width
        spacing: 4
        Text { text: title; color: dock.mute; font.pixelSize: 11 }
        Row {
            spacing: 4
            Repeater {
                model: ["R", "G", "B", "A"]
                delegate: Row {
                    required property string modelData
                    required property int index
                    spacing: 2
                    Text { text: modelData; color: dock.mute; font.pixelSize: 11; anchors.verticalCenter: parent.verticalCenter }
                    Rectangle {
                        width: 40
                        height: 28
                        radius: 6
                        color: Qt.rgba(0, 0, 0, bridge.dark ? 0.28 : 0.06)
                        TextInput {
                            anchors.fill: parent
                            horizontalAlignment: TextInput.AlignHCenter
                            verticalAlignment: TextInput.AlignVCenter
                            color: dock.ink
                            font.pixelSize: 12
                            text: activeFocus ? text : String((ch && ch[index]) || 0)
                            validator: IntValidator { bottom: 0; top: 255 }
                            onEditingFinished: bridge.setChannel(which, index, Number(text))
                        }
                    }
                }
            }
            Rectangle {
                width: 28
                height: 28
                radius: 6
                color: Qt.rgba((ch[0] || 0) / 255, (ch[1] || 0) / 255, (ch[2] || 0) / 255, 1)
                TapHandler { onTapped: bridge.clickId(pick) }
            }
        }
    }
}
