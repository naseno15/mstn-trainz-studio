import QtQuick

Item {
    id: root

    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            GradientStop { position: 0.0; color: bridge.dark ? "#1c2430" : "#f7f8fb" }
            GradientStop { position: 0.45; color: bridge.dark ? "#12161c" : "#e8edf3" }
            GradientStop { position: 1.0; color: bridge.dark ? "#0a0c10" : "#d5dbe3" }
        }
    }

    Column {
        id: hubCol
        anchors.centerIn: parent
        spacing: 10
        width: Math.min(parent.width - 48, 1280)

        Image {
            anchors.horizontalCenter: parent.horizontalCenter
            source: "image://mstnlogo/" + (bridge.dark ? "dark" : "light")
            sourceSize.width: 180
            fillMode: Image.PreserveAspectFit
            width: 180
            height: 56
        }

        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: (typeof bridge.brand === "string" ? qsTr(bridge.brand) : bridge.brand)
            color: bridge.dark ? "#f2f4f8" : "#1d1d1f"
            font.pixelSize: 30
            font.bold: true
        }
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: (typeof bridge.sub === "string" ? qsTr(bridge.sub) : bridge.sub)
            color: bridge.dark ? "#9aa3b2" : "#5c6570"
            font.pixelSize: 12
        }

        Item { width: 1; height: 8 }

        Row {
            anchors.horizontalCenter: parent.horizontalCenter
            spacing: 16
            Repeater {
                model: bridge.cards
                delegate: GlassPlate {
                    id: card
                    required property string studioId
                    required property string title
                    required property string blurb
                    required property string glyph
                    width: Math.min(188, Math.floor((hubCol.width - 12 * Math.max(0, bridge.cards.length - 1)) / Math.max(1, bridge.cards.length)))
                    height: 188
                    dark: bridge.dark
                    lit: cardHover.hovered
                    scale: cardHover.hovered ? 1.035 : 1.0
                    Behavior on scale { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }

                    Column {
                        anchors.centerIn: parent
                        spacing: 8
                        width: parent.width
                        Text {
                            anchors.horizontalCenter: parent.horizontalCenter
                            text: (typeof card.glyph === "string" ? qsTr(card.glyph) : card.glyph)
                            font.family: bridge.iconFont
                            font.pixelSize: 28
                            color: "#ff5a1f"
                        }
                        Text {
                            anchors.horizontalCenter: parent.horizontalCenter
                            width: parent.width
                            horizontalAlignment: Text.AlignHCenter
                            text: (typeof card.title === "string" ? qsTr(card.title) : card.title)
                            color: bridge.dark ? "#f4f6fa" : "#1d1d1f"
                            font.pixelSize: 15
                            font.bold: true
                            wrapMode: Text.WordWrap
                        }
                        Text {
                            anchors.horizontalCenter: parent.horizontalCenter
                            width: parent.width
                            horizontalAlignment: Text.AlignHCenter
                            text: (typeof card.blurb === "string" ? qsTr(card.blurb) : card.blurb)
                            color: bridge.dark ? "#a8b0bd" : "#5c6570"
                            font.pixelSize: 11
                            wrapMode: Text.WordWrap
                        }
                        Text {
                            anchors.horizontalCenter: parent.horizontalCenter
                            text: (typeof bridge.cta === "string" ? qsTr(bridge.cta) : bridge.cta)
                            color: "#ff5a1f"
                            font.pixelSize: 11
                            font.bold: true
                        }
                    }

                    HoverHandler { id: cardHover }
                    TapHandler {
                        onTapped: bridge.openStudio(card.studioId)
                    }
                }
            }
        }

        Item { width: 1; height: 6 }

        GlassPlate {
            anchors.horizontalCenter: parent.horizontalCenter
            width: Math.min(parent.width, 860)
            height: 92
            dark: bridge.dark
            lit: dropHover.containsDrag
            plateRadius: 18

            Column {
                anchors.centerIn: parent
                spacing: 2
                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: (typeof bridge.dropTitle === "string" ? qsTr(bridge.dropTitle) : bridge.dropTitle)
                    color: bridge.dark ? "#f2f4f8" : "#1d1d1f"
                    font.pixelSize: 13
                    font.bold: true
                }
                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: (typeof bridge.dropHint === "string" ? qsTr(bridge.dropHint) : bridge.dropHint)
                    color: bridge.dark ? "#9aa3b2" : "#5c6570"
                    font.pixelSize: 11
                }
            }

            DropZone {
                id: dropHover
                anchors.fill: parent
                onFilesDropped: function (drop) {
                    var urls = []
                    for (var i = 0; i < drop.urls.length; ++i)
                        urls.push(String(drop.urls[i]))
                    bridge.dropUrls(urls)
                    drop.acceptProposedAction()
                }
            }
        }

        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: (typeof bridge.copy === "string" ? qsTr(bridge.copy) : bridge.copy)
            color: bridge.dark ? "#6d7684" : "#8b939e"
            font.pixelSize: 10
        }
    }
}
