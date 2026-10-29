include $(TOPDIR)/rules.mk

PKG_NAME:=mihomo-yala
PKG_VERSION:=1.19.33
PKG_RELEASE:=1
PKG_SOURCE:=mihomo-linux-arm64-v$(PKG_VERSION).gz
PKG_SOURCE_URL:=https://github.com/MetaCubeX/mihomo/releases/download/v$(PKG_VERSION)
PKG_HASH:=ba408b317080ee265c46cb923a50018c1b82cbd708551cdd46a1e3e307396187
PKG_BUILD_DIR:=$(BUILD_DIR)/$(PKG_NAME)-$(PKG_VERSION)
PKG_LICENSE:=GPL-3.0-only
PKG_LICENSE_FILES:=

include $(INCLUDE_DIR)/package.mk

define Package/mihomo-yala
  SECTION:=net
  CATEGORY:=Network
  TITLE:=Pinned official Mihomo arm64 core for the YALA RD03v2 image
  DEPENDS:=+ca-bundle
endef

define Build/Prepare
	mkdir -p $(PKG_BUILD_DIR)
	gzip -dc $(DL_DIR)/$(PKG_SOURCE) > $(PKG_BUILD_DIR)/clash_meta
endef

define Build/Configure
endef

define Build/Compile
endef

define Package/mihomo-yala/install
	$(INSTALL_DIR) $(1)/etc/openclash/core
	$(INSTALL_BIN) $(PKG_BUILD_DIR)/clash_meta $(1)/etc/openclash/core/clash_meta
endef

$(eval $(call BuildPackage,mihomo-yala))
