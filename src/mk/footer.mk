define FOOTER
SUBDIRS_$(d) := $(patsubst %/,%,$(addprefix $(d)/,$(SUBDIRS)))


CLEAN_$(d) := $(CLEAN_$(d)) $(filter /%,$(CLEAN) $(TARGETS)) $(addprefix $(d)/,$(filter-out /%,$(CLEAN)))

# Replacing DOLLARESCAPE_ with '$$$$$$$' ensures '$' survives multiple make expansion passes, eventually produces a literal '$' when it reaches recipe 
# Similarly Replacing HASHESCAPE_ with '\#'  
define escape_specials
$(subst DOLLARESCAPE_,$$$$$$$,$(subst HASHESCAPE_,\#,$(1)))
endef

# Escape specials for a source or dependency, deciding from the $(d)/ directory prefix.
#
# A source directory file carries that prefix, so it is unescaped for make to find it on
# disk. Anything else names an object in the library and keeps its escaped form
# (HASHESCAPE_, DOLLARESCAPE_) so that it matches the target name generated for it.
#
# The extension cannot be used to tell the two apart: a pseudo-source recipe reads its
# source from a file whose extension names an object type, e.g. S\#CMD.CMD: S\#CMD.CMD
define escape_source
$(if $(filter $(d)/%,$(1)),$(call escape_specials,$(1)),$(1))
endef

ifdef TARGETS
TARGETS_$(d) := $(TARGETS)
$(foreach tgt,$(TARGETS),$(eval vpath $(tgt) $(OBJPATH_$(d)))$(eval $(tgt)_d = $(d))$(eval $(call generate_rule,$(tgt),$(call escape_source,$($(tgt)_SRC)),$(foreach dep,$($(tgt)_DEP),$(call escape_source,$(dep))),$($(tgt)_RECIPE))))
endif


########################################################################
# Inclusion of subdirectories rules - only after this line one can     #
# refer to subdirectory targets and so on.                             #
########################################################################
$(foreach sd,$(SUBDIRS),$(eval $(call include_subdir_rules,$(sd))))

.PHONY: dir_$(d) clean_$(d) clean_extra_$(d) clean_tree_$(d) dist_clean_$(d)
.SECONDARY: $(OBJPATH)

# Whole tree targets
all :: $(TARGETS_$(d))

clean_all :: clean_$(d)

# dist_clean is optimized in skel.mk if we are building in out of project tree
ifeq ($(strip $(TOP_BUILD_DIR)),)
dist_clean :: dist_clean_$(d)

# No point to enforce clean_extra dependency if CLEAN is empty
ifeq ($(strip $(CLEAN_$(d))),)
dist_clean_$(d) :
else
dist_clean_$(d) : clean_extra_$(d)
endif
	rm -rf $(DIST_CLEAN_DIR)
endif

########################################################################
#                        Per directory targets                         #
########################################################################

clean_$(d) :
	$(info cleaning $(CLEAN_DIR))

clean_tree_$(d) : clean_$(d) $(foreach sd,$(SUBDIRS_$(d)),clean_tree_$(sd))

# Skip the target rules generation and inclusion of the dependencies
# when we just want to clean up things :)
ifeq ($(filter clean clean_% dist_clean,$(MAKECMDGOALS)),)

SUBDIRS_TGTS := $(foreach sd,$(SUBDIRS_$(d)),$(TARGETS_$(sd)))

# Target rules for all "non automatic" targets
# $(foreach tgt,$(filter-out $(AUTO_TGTS),$(TARGETS_$(d))),$(eval $(call tgt_rule,$(tgt))))

# Way to build all targets in given subtree (not just current dir as via
# dir_$(d) - see below)
tree_$(d) : $(TARGETS_$(d)) $(foreach sd,$(SUBDIRS_$(d)),tree_$(sd))

# If the directory is just for grouping its targets will be targets from
# all subdirectories
ifeq ($(strip $(TARGETS_$(d))),)
TARGETS_$(d) := $(SUBDIRS_TGTS)
endif

# This is a default rule - see Makefile
dir_$(d) : $(TARGETS_$(d))

slashify = $(subst _,/,$(1))

.SECONDEXPANSION:
dir_% : dir_$$(TOP)/$$(call slashify,$$(subst dir_,,$$(@)))
	@echo

endif
endef
