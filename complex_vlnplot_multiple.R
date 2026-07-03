suppressMessages(suppressWarnings({
  require(ggplot2)
  require(reshape2)
  require(ggrastr)
  require(grid)
  require(ggbeeswarm)
}))
args = commandArgs(trailingOnly = TRUE)
if(length(args)<6){
  message("Error: too few input args, (",paste(args,collapse=", "),")")
}
libPath = tail(args,1)
if(nchar(libPath)>4){
  addPath <- unlist(strsplit(libPath,";"))
  addPath <- addPath[sapply(addPath,dir.exists)]
  .libPaths(c(addPath,.libPaths()))
}

strCSV <- args[1]
genes <- unlist(strsplit(args[2],","))
cluster <- args[3]
grp <- args[4]
imgW <- as.numeric(args[5])
imgH <- as.numeric(args[6])
i <- 7
strFun <- args[i]
fontsize <- as.numeric(args[i+1])
dpi <- as.numeric(args[i+2])

gene_count <- as.data.frame(data.table::fread(strCSV))
cellID <- colnames(gene_count)[1]
cellN <- nrow(gene_count)
gene_count <- reshape2::melt(gene_count, id.vars = c(cellID,cluster,grp), measure.vars = genes,
                             variable.name = "Genes", value.name = "Expr")
gene_count$Genes<-factor(gene_count$Genes,levels = genes)

change_strip_background <- function(ggplt_obj, type = "top", strip.color=NULL) {
  g <- ggplot_gtable(ggplot_build(ggplt_obj))
  if (type == "top") {
    strip_idx <- grep("^strip-t", g$layout$name)
  } else if (type == "right") {
    strip_idx <- grep("^strip-r", g$layout$name)
  } else {
    strip_idx <- c(grep("^strip-t", g$layout$name), grep("^strip-r", g$layout$name))
  }
  if (length(strip_idx) == 0) return(g)
  fills <- strip.color
  if (is.null(fills)) {
    n_t <- sum(grepl("^strip-t", g$layout$name))
    n_r <- sum(grepl("^strip-r", g$layout$name))
    fills <- c(scales::hue_pal(l=90)(n_t), scales::hue_pal(l=90)(n_r))
  }
  for (k in seq_along(strip_idx)) {
    i <- strip_idx[k]
    # ggplot2 < 3.5: childrenOrder; >= 3.5: children
    if (!is.null(g$grobs[[i]]$grobs[[1]]$childrenOrder)) {
      j <- which(grepl('rect', g$grobs[[i]]$grobs[[1]]$childrenOrder))
      if (length(j) > 0)
        g$grobs[[i]]$grobs[[1]]$children[[j[1]]]$gp$fill <- fills[k]
    } else {
      child_names <- names(g$grobs[[i]]$grobs[[1]]$children)
      j <- which(grepl('rect', child_names, ignore.case = TRUE))
      if (length(j) > 0)
        g$grobs[[i]]$grobs[[1]]$children[[j[1]]]$gp$fill <- fills[k]
    }
  }
  g
}

alpha <- 0.01
strip.color <- NULL
font.size <- fontsize
pt.size <- 0.1
p <- ggplot(gene_count, aes(.data[[grp]], .data[["Expr"]], fill = .data[[grp]])) +
  geom_violin(scale = 'width', adjust = 1, trim = TRUE, linewidth=0.3, alpha=0.5, color="pink") +
  rasterise(geom_quasirandom(size=pt.size, alpha=alpha), dpi=dpi) +
  scale_y_continuous(expand = c(0, 0), position="left", labels = function(x)
    c(rep(x = "", times = max(0, length(x)-2)), x[max(1, length(x)-1)], "")) +
  facet_grid(as.formula(paste(cluster, "~Genes")), scales = 'free_x') +
  xlab("") + ylab("") + ggtitle(paste(cellN, "cells")) +
  theme(panel.background = element_rect(fill = "white", colour = "black"),
        axis.title = element_text(size = font.size),
        axis.text.x = element_text(size = font.size, angle = 45, hjust = 1, vjust = 1),
        axis.text.y = element_text(size = (font.size)),
        strip.text = element_text(size = font.size-3),
        legend.title = element_blank(),
        legend.position = 'none')
tmp_dev <- tempfile(fileext = ".png")
png(tmp_dev, width = imgW, height = imgH, units = "in", res = dpi)
g <- tryCatch(
  change_strip_background(p, type = 'both', strip.color = strip.color),
  error = function(e) ggplot_gtable(ggplot_build(p))
)
dev.off()
unlink(tmp_dev)

strImg <- gsub("csv$", strFun, strCSV)
f <- get(strFun)
f(strImg, width=imgW, height=imgH, units='in', res=dpi)
grid::grid.draw(g)
a <- dev.off()
fig <- base64enc::dataURI(file = strImg)
cat(gsub("data:;base64,", "", fig))
a <- file.remove(strImg)
